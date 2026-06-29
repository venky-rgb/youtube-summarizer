import streamlit as st
import yt_dlp
import requests
from pymongo import MongoClient
import re

# ==============================================================================
# 1. DATABASE & API CONFIGURATION (Streamlit Secrets)
# ==============================================================================
# Retrieve MongoDB URI and Ollama Cloud Credentials from Secrets
MONGO_URI = st.secrets["MONGO_URI"]
OLLAMA_API_KEY = st.secrets["OLLAMA_API_KEY"]

# Initialize MongoDB Client connection
client = MongoClient(MONGO_URI)
db = client['youtube_summarizer_db']  # Database Name
collection = db['summaries']          # Collection Name

# ==============================================================================
# 2. HELPER FUNCTIONS (Subtitle Fetching & Summarization)
# ==============================================================================
def get_clean_video_id(url):
    """Extracts clean 11-character video ID from any standard YouTube URL link."""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_transcript(video_url):
    """Fetches full text transcripts securely using yt-dlp bypassing IP locks."""
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            subtitles = info.get('subtitles', {}) or info.get('automatic_captions', {})
            
            if 'en' in subtitles:
                # Target the JSON-formatted transcript tracks if available
                en_subs = subtitles['en']
                json_track = next((sub for sub in en_subs if sub.get('ext') == 'json'), en_subs[0])
                sub_url = json_track['url']
                
                # Fetch content payload directly from YouTube endpoints
                response = requests.get(sub_url)
                if response.status_code == 200:
                    data = response.json()
                    # Parse internal string fragments out of nested structures cleanly
                    text_segments = [
                        seg['utf8'] 
                        for event in data.get('events', []) 
                        for seg in event.get('segs', []) 
                        if 'utf8' in seg and seg['utf8'].strip()
                    ]
                    full_text = " ".join(text_segments)
                    # Clean up random mid-word formatting bugs
                    return re.sub(r'\s+', ' ', full_text).strip()
    except Exception as e:
        st.sidebar.error(f"Extraction error: {e}")
    return None

def generate_summary_with_ollama(transcript_text):
    """Sends raw transcripts over to Ollama's Cloud infrastructure API for synthesis."""
    # Replace with your actual Ollama host cloud endpoint route setup
    ollama_url = "https://api.ollama.cloud/v1/chat/completions" 
    
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama3", # Or whichever active base model your script uses
        "messages": [
            {"role": "system", "content": "Provide an organized, clear summary of this video transcript using clean bullet points."},
            {"role": "user", "content": transcript_text}
        ],
        "stream": False
    }
    
    try:
        res = requests.post(ollama_url, json=payload, headers=headers)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Summarization Error: {e}"
    return "Failed to process text using Ollama cloud resources."

# ==============================================================================
# 3. USER INTERFACE (Streamlit Front-End)
# ==============================================================================
st.set_page_config(page_title="Fast & Structured Video Summarizer", page_icon="📺", layout="wide")

# Sidebar - Fetch and show past entries from MongoDB Atlas
st.sidebar.title("📝 History (MongoDB)")
try:
    past_summaries = list(collection.find().sort("_id", -1))
    if past_summaries:
        for item in past_summaries:
            with st.sidebar.expander(item.get('title', 'Saved Summary')):
                st.write(item.get('summary'))
    else:
        st.sidebar.info("No past summaries found in MongoDB.")
except Exception as mongo_err:
    st.sidebar.error(f"Database sync issue: {mongo_err}")

# Main Window Form Layout
st.title("📺 Fast & Structured Video Summarizer")
st.caption("Extracts transcripts cleanly using yt-dlp and builds organized notes using Ollama & MongoDB.")

video_input = st.text_input("Enter YouTube Video URL:", placeholder="https://www.youtube.com/watch?v=...")

if st.button("Summarize Video", type="primary"):
    if not video_input.strip():
        st.warning("Please enter a valid link first.")
    else:
        video_id = get_clean_video_id(video_input)
        if not video_id:
            st.error("Invalid YouTube link format.")
        else:
            with st.spinner("Extracting dialogue tracks from video processing engines..."):
                transcript = get_youtube_transcript(video_input)
                
            if not transcript:
                st.error("No subtitles found. Please verify the video has English audio/captions.")
            else:
                with st.spinner("Ollama is synthesizing notes structure..."):
                    summary_result = generate_summary_with_ollama(transcript)
                    
                st.success("Summary Completed!")
                st.markdown("### 📋 Executive Summary")
                st.write(summary_result)
                
                # Automatically save the clean workspace snapshot up into your database
                try:
                    collection.insert_one({
                        "video_id": video_id,
                        "title": f"Video Summary ({video_id})",
                        "summary": summary_result,
                        "transcript_preview": transcript[:200] + "..."
                    })
                    st.toast("Summary saved safely to MongoDB Atlas!")
                    st.rerun() # Refresh layout smoothly to reflect new history index element
                except Exception as save_err:
                    st.error(f"Failed to record data object into Atlas cloud: {save_err}")