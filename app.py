import streamlit as st
import subprocess
import os
import glob
import webvtt
from datetime import datetime
from ollama import Client  # Official Ollama SDK library
from pymongo import MongoClient  # MongoDB Python Driver
import certifi  # Safe SSL verification handling for remote cloud connections

# --- INITIALIZE PERSISTENT STATE ---
if "current_summary" not in st.session_state:
    st.session_state.current_summary = ""

# --- STREAMLIT NATIVE SECRETS CONFIGURATION ---
if "OLLAMA_API_KEY" in st.secrets:
    api_key = st.secrets["OLLAMA_API_KEY"]
else:
    api_key = os.environ.get("OLLAMA_API_KEY")

if "MONGO_URI" in st.secrets:
    MONGO_URI = st.secrets["MONGO_URI"]
else:
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")

# --- MONGO DATABASE CONFIGURATION ---
def get_mongo_collection():
    """Establishes connection and returns the MongoDB collection target."""
    if "localhost" in MONGO_URI or "127.0.0.1" in MONGO_URI:
        client = MongoClient(MONGO_URI)
    else:
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client["youtube_summarizer_db"]
    return db["summaries"]

def save_summary_to_mongo(url, summary_text):
    """Inserts a generated video summary document into MongoDB."""
    try:
        collection = get_mongo_collection()
        document = {
            "video_url": url,
            "summary": summary_text,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        collection.insert_one(document)
    except Exception as e:
        st.error(f"Database write failed: {e}")

def get_past_summaries_from_mongo():
    """Retrieves all previous summaries from MongoDB sorted by newest first."""
    try:
        collection = get_mongo_collection()
        return list(collection.find().sort("_id", -1))
    except Exception as e:
        st.sidebar.error(f"Failed to load database history: {e}")
        return []

def flush_mongo_database():
    """Deletes all documents from the summaries collection."""
    try:
        collection = get_mongo_collection()
        collection.delete_many({})
        return True
    except Exception as e:
        st.sidebar.error(f"Failed to clear database: {e}")
        return False

# --- STREAMLIT GRAPHICAL INTERFACE ---
st.set_page_config(page_title="AI Video Summarizer", page_icon="📺", layout="wide")
st.title("📺 Fast & Structured Video Summarizer")
st.write("Extracts transcripts locally and builds organized notes using Ollama's Cloud API & MongoDB.")

# --- SIDEBAR ENGINE ---
st.sidebar.header("📜 History (MongoDB Compass)")
past_records = get_past_summaries_from_mongo()

if past_records:
    for record in past_records:
        url = record.get("video_url", "Unknown URL")
        summary = record.get("summary", "")
        timestamp = record.get("created_at", "")
        
        with st.sidebar.expander(f"🎬 {url[:30]}... ({timestamp})"):
            st.write(summary)
            
    st.sidebar.markdown("---")
    # ADDED: Flush Button targeting database cleaning
    if st.sidebar.button("🗑️ Flush History Database", type="secondary", use_container_width=True):
        if flush_mongo_database():
            st.session_state.current_summary = ""  # Clear active main window display
            st.sidebar.success("Database Flushed Successfully!")
            st.rerun()
else:
    st.sidebar.info("No past summaries found in MongoDB.")

# --- MAIN CONTROLS ENGINE ---
video_url = st.text_input("Enter YouTube Video URL:", value="")

def clean_up_files():
    """Wipes out cached sub tracks from storage to stay space-efficient."""
    for f in glob.glob("temp_sub*"):
        try: os.remove(f)
        except: pass

if st.button("Summarize Video", type="primary"):
    if not api_key:
        st.error("Missing Ollama Cloud API Key! Please verify your configuration in '.streamlit/secrets.toml'.")
    elif video_url.strip():
        clean_up_files()
        st.session_state.current_summary = ""  
        
        with st.spinner("Step 1: Extracting timeline transcript tracks..."):
            command = [
                "yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
                "--sub-lang", "en", "--output", "temp_sub", video_url
            ]
            subprocess.run(command, capture_output=True, text=True)
            
            sub_files = glob.glob("temp_sub.en.*")
            full_transcript = ""
            
            if sub_files and os.path.exists(sub_files[0]):
                try:
                    vtt = webvtt.read(sub_files[0])
                    cleaned_lines = []
                    
                    for caption in vtt:
                        text = caption.text.strip().replace('\n', ' ')
                        if text:
                            if cleaned_lines and text.startswith(cleaned_lines[-1]):
                                cleaned_lines[-1] = text
                            elif cleaned_lines and cleaned_lines[-1].startswith(text):
                                continue
                            else:
                                cleaned_lines.append(text)
                                
                    full_transcript = " ".join(cleaned_lines)
                except Exception as e:
                    st.error(f"Parsing error: {e}")
            else:
                st.error("No subtitles found. Please verify the video has English audio/captions.")

        if full_transcript:
            st.subheader("📋 Organized Video Breakdown:")
            output_container = st.empty()
            live_text = ""
            
            try:
                cloud_client = Client(
                    host="https://ollama.com",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                
                prompt_structure = (
                    "You are a technical note-taking assistant. Summarize the transcript below into an organized structure. "
                    "CRITICAL FORMATTING RULE: For side headings, do NOT use bold bullet points. Instead, use bold text prefixed with '🔹 ' (e.g., 🔹 **High-level nature:**). "
                    "List the details belonging to that heading directly underneath it using indented bullet points.\n\n"
                    f"Transcript:\n{full_transcript[:6000]}"
                )
                
                response_stream = cloud_client.chat(
                    model="gpt-oss:120b",
                    messages=[{"role": "user", "content": prompt_structure}],
                    stream=True
                )
                
                for chunk in response_stream:
                    token = chunk['message']['content']
                    if token:
                        live_text += token
                        output_container.write(live_text)
                    
                if live_text.strip():
                    save_summary_to_mongo(video_url, live_text)
                    st.session_state.current_summary = live_text
                    st.success("Notes Generated & Saved to MongoDB Compass!")
                    st.rerun()  
                else:
                    st.error("The model responded with empty content. Please verify your token state on ollama.com.")
                
            except Exception as e:
                st.error(f"Ollama Cloud interaction failed: {e}")
                    
        clean_up_files()
    else:
        st.warning("Please paste a link first!")

# --- DISPLAY PERSISTED RESULTS ENGINE ---
if st.session_state.current_summary:
    st.subheader("📋 Active Video Notes:")
    st.markdown(st.session_state.current_summary)