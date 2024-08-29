import os
import shutil
import zipfile
import subprocess
import streamlit as st
from pathlib import Path
from typing import List
import platform
import psutil
import GPUtil

# Utility Functions for System Info

def get_system_info():
    """Retrieve and format system information."""
    system_info = platform.uname()
    cpu_info = platform.processor()
    cpu_count = psutil.cpu_count(logical=False)
    logical_cpu_count = psutil.cpu_count(logical=True)
    memory_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage('/')
    
    # Collect GPU information
    gpus = GPUtil.getGPUs()
    gpu_info = []
    if gpus:
        for i, gpu in enumerate(gpus):
            gpu_info.append({
                "ID": gpu.id,
                "Name": gpu.name,
                "Driver": gpu.driver,
                "GPU Memory Total": f"{gpu.memoryTotal} MB",
                "GPU Memory Free": f"{gpu.memoryFree} MB",
                "GPU Memory Used": f"{gpu.memoryUsed} MB",
                "GPU Load": f"{gpu.load * 100}%",
                "GPU Temperature": f"{gpu.temperature}°C"
            })
    else:
        gpu_info.append({"No GPU detected": ""})
    
    return {
        "System": system_info.system,
        "Node Name": system_info.node,
        "Release": system_info.release,
        "Version": system_info.version,
        "Machine": system_info.machine,
        "Processor": cpu_info,
        "Physical Cores": cpu_count,
        "Logical Cores": logical_cpu_count,
        "Total Memory": f"{memory_info.total} bytes",
        "Available Memory": f"{memory_info.available} bytes",
        "Used Memory": f"{memory_info.used} bytes",
        "Memory Utilization": f"{memory_info.percent}%",
        "Total Disk Space": f"{disk_info.total} bytes",
        "Used Disk Space": f"{disk_info.used} bytes",
        "Free Disk Space": f"{disk_info.free} bytes",
        "Disk Space Utilization": f"{disk_info.percent}%"
    }, gpu_info

# Streamlit App

def main():
    st.title("Bulk Video Processor and System Info")

    # Display system information
    st.header("System Information")
    system_info, gpu_info = get_system_info()
    
    st.write("### System Details")
    for key, value in system_info.items():
        st.write(f"{key}: {value}")

    st.write("### GPU Details")
    for gpu in gpu_info:
        for key, value in gpu.items():
            st.write(f"{key}: {value}")
# Utility Functions

def run_ffmpeg_command(cmd):
    """Run an ffmpeg command and handle errors."""
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Error running ffmpeg command: {e}")
        raise

def extract_zip(zip_path, extract_to):
    """Extract a ZIP file to a specified directory."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    st.write(f"Extracted ZIP file to {extract_to}")

def trim_video_ffmpeg(input_path, output_path, start_time, end_time):
    """Trim a video using ffmpeg with GPU acceleration."""
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ss', str(start_time),
        '-to', str(end_time),
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-y',
        output_path
    ]
    run_ffmpeg_command(cmd)
    st.write(f"Trimmed video saved to {output_path}")

def split_video_ffmpeg(input_path, split_times, output_dir):
    """Split a video into segments based on provided times."""
    segments = []
    for i, (start, end) in enumerate(split_times):
        segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
        trim_video_ffmpeg(input_path, segment_path, start, end)
        segments.append(segment_path)
    return segments

def concatenate_videos_ffmpeg(video_files, output_path):
    """Concatenate multiple videos using ffmpeg with GPU acceleration."""
    with open('file_list.txt', 'w') as file:
        for video in video_files:
            file.write(f"file '{video}'\n")

    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'file_list.txt',
        '-c:v', 'h264_nvenc',
        '-preset', 'fast',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-y',
        output_path
    ]
    run_ffmpeg_command(cmd)
    st.write(f"Concatenated video saved to {output_path}")
    os.remove('file_list.txt')

def insert_clip(base_video, clip_to_insert, position, output_path):
    """Insert a clip into a base video at a specified position."""
    temp_video_path = 'temp_concat.mp4'
    if position == 'start':
        cmd = [
            'ffmpeg',
            '-i', clip_to_insert,
            '-i', base_video,
            '-filter_complex', '[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]',
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-y',
            temp_video_path
        ]
    elif position == 'end':
        cmd = [
            'ffmpeg',
            '-i', base_video,
            '-i', clip_to_insert,
            '-filter_complex', '[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]',
            '-map', '[outv]',
            '-map', '[outa]',
            '-c:v', 'h264_nvenc',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-y',
            temp_video_path
        ]
    elif position == 'between':
        segment_list = [base_video] + [clip_to_insert] + [base_video]  # Example for demonstration
        concatenate_videos_ffmpeg(segment_list, temp_video_path)
    
    run_ffmpeg_command(cmd)
    st.write(f"Video with inserted clip saved to {output_path}")

# Streamlit App

@st.cache_data
def process_videos(zip_files, split_times, clips_to_insert, insert_position):
    """Process videos from ZIP files: split, insert clips, and concatenate."""
    temp_extract_dir = 'temp_extracted'
    if not os.path.exists(temp_extract_dir):
        os.makedirs(temp_extract_dir)

    # Extract ZIP files
    for zip_file in zip_files:
        with open(zip_file.name, 'wb') as f:
            f.write(zip_file.getvalue())
        extract_zip(zip_file.name, temp_extract_dir)
        os.remove(zip_file.name)

    # Split videos
    all_segments = []
    for filename in os.listdir(temp_extract_dir):
        file_path = os.path.join(temp_extract_dir, filename)
        if filename.endswith((".mp4", ".avi", ".mov", ".mkv")):
            segments = split_video_ffmpeg(file_path, split_times, temp_extract_dir)
            all_segments.extend(segments)

    # Insert clips and concatenate
    final_output = 'final_output.mp4'
    for clip_to_insert in clips_to_insert:
        if insert_position in ['start', 'end']:
            temp_output = 'temp_with_insert.mp4'
            insert_clip(all_segments[0], clip_to_insert, insert_position, temp_output)  # Example for first segment
            all_segments = [temp_output] + all_segments[1:] if insert_position == 'start' else all_segments + [temp_output]
        elif insert_position == 'between':
            segment_list = [all_segments[0]] + [clip_to_insert] + all_segments[1:]
            concatenate_videos_ffmpeg(segment_list, 'temp_with_insert.mp4')
            all_segments = [temp_output] + all_segments[1:]

    if all_segments:
        concatenate_videos_ffmpeg(all_segments, final_output)

    shutil.rmtree(temp_extract_dir)
    return final_output

def main():
    st.title("Bulk Video Processor")

    st.header("Upload ZIP Files")
    zip_files = st.file_uploader("Upload ZIP files", type=["zip"], accept_multiple_files=True)

    split_times_input = st.text_input("Split Times (e.g., 0,10;20,30)", "0,10;20,30")
    clips_to_insert = st.file_uploader("Upload Clips to Insert", type=["mp4"], accept_multiple_files=True)
    insert_position = st.selectbox("Insert Position", ["start", "end", "between"])

    if st.button("Process Videos"):
        if zip_files and clips_to_insert:
            try:
                split_times = [tuple(map(float, time_range.split(','))) for time_range in split_times_input.split(';')]
                with st.spinner("Processing videos..."):
                    output_file = process_videos(zip_files, split_times, clips_to_insert, insert_position)
                    st.success(f"Processing complete! Download the final video: {output_file}")
                    st.video(output_file)
            except Exception as e:
                st.error(f"An error occurred: {e}")
        else:
            st.error("Please upload ZIP files and clips to insert.")

if __name__ == "__main__":
    main()
