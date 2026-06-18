import streamlit as st
import ollama
import subprocess
import os
import glob
import webvtt

st.set_page_config(page_title="AI Video Summarizer", page_icon="📺", layout="wide")
st.title("📺 Fast & Structured Video Summarizer")
st.write("Extracts transcripts locally and instantly builds organized notes.")

video_url = st.text_input("Enter YouTube Video URL:", value="")

def clean_up_files():
    for f in glob.glob("temp_sub*"):
        try: os.remove(f)
        except: pass

if st.button("Summarize Video", type="primary"):
    if video_url.strip():
        clean_up_files()
        
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
            
            # Setup a live visual container for streaming text
            output_container = st.empty()
            live_text = ""
            
            try:
                prompt_structure = (
                    "You are a technical note-taking assistant. Summarize the transcript below into an organized structure. "
                    "CRITICAL FORMATTING RULE: For side headings, do NOT use bullet points. Instead, use bold text prefixed with '🔹 ' (e.g., 🔹 **High-level nature:**). "
                    "List the details belonging to that heading directly underneath it using indented bullet points.\n\n"
                    f"Transcript:\n{full_transcript[:6000]}" # Slightly tightened context boundary to accelerate processing
                )
                
                # Request a live stream from Ollama
                response_stream = ollama.chat(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": prompt_structure}],
                    options={
                        "temperature": 0.1,    # Kept low for deterministic, fast output
                        "num_predict": 400,    # Strictly caps length to prevent model rambling
                        "num_thread": 4        # Forces CPU parallelization if GPU is unavailable
                    },
                    stream=True
                )
                
                # Render tokens on-screen the millisecond they are calculated
                for chunk in response_stream:
                    token = chunk['message']['content']
                    live_text += token
                    output_container.write(live_text)
                    
                st.success("Notes Generated!")
                
            except Exception as e:
                st.error(f"Local LLM connection failed: {e}")
                    
        clean_up_files()
    else:
        st.warning("Please paste a link first!")