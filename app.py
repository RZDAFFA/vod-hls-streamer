import os
import shutil
import subprocess
import asyncio
import logging
import re
import psutil
from pathlib import Path
from typing import Dict, Optional
import uuid
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VOD HLS Streamer - Intel J5005 Optimized", version="1.0.0")

# Configuration untuk Intel Pentium J5005
class Config:
    UPLOAD_FOLDER = "uploads"
    OUTPUT_FOLDER = "output"
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
    ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".ts"}
    
    # HLS Settings - optimized for low CPU
    HLS_TIME = 6  # 6 detik per segment
    HLS_LIST_SIZE = 5  # 5 segments in playlist
    
    # Encoding settings - COPY MODE (no transcoding)
    # Hanya re-wrap ke HLS container, tidak encode ulang
    USE_COPY_MODE = True  # Set False jika perlu transcoding
    
    # Jika perlu transcoding (USE_COPY_MODE = False):
    VIDEO_CODEC = "libx264"
    VIDEO_PRESET = "ultrafast"
    VIDEO_CRF = "28"
    VIDEO_MAXRATE = "800k"
    AUDIO_CODEC = "aac"
    AUDIO_BITRATE = "96k"
    
    # Hardware acceleration (Intel Quick Sync)
    USE_QSV = True  # Auto-detect QSV availability
    
    MAX_CONCURRENT_STREAMS = 10  # J5005 bisa handle banyak copy-mode streams

config = Config()

# Create directories
Path(config.UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(config.OUTPUT_FOLDER).mkdir(exist_ok=True)

# Store active streams
active_streams: Dict[str, subprocess.Popen] = {}
stream_metadata: Dict[str, dict] = {}

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Serve output files
app.mount("/output", StaticFiles(directory=config.OUTPUT_FOLDER), name="output")

class StreamResponse(BaseModel):
    stream_id: str
    stream_url: str
    status: str
    mode: str  # "copy" or "transcode"

def check_qsv_available():
    """Check if Intel Quick Sync Video is available"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "qsv" in result.stdout
    except:
        return False

def get_video_info(file_path: str) -> dict:
    """Get video information using ffprobe"""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            
            video_stream = next((s for s in data.get('streams', []) if s['codec_type'] == 'video'), None)
            audio_stream = next((s for s in data.get('streams', []) if s['codec_type'] == 'audio'), None)
            
            return {
                'duration': float(data.get('format', {}).get('duration', 0)),
                'size': int(data.get('format', {}).get('size', 0)),
                'video_codec': video_stream.get('codec_name') if video_stream else None,
                'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                'width': video_stream.get('width') if video_stream else None,
                'height': video_stream.get('height') if video_stream else None,
                'bitrate': int(data.get('format', {}).get('bit_rate', 0))
            }
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
    
    return {}

def can_use_copy_mode(video_info: dict) -> bool:
    """
    Determine if we can use copy mode (no transcoding needed)
    Copy mode requires: H264 video + AAC audio
    """
    if not video_info:
        return False
    
    video_codec = video_info.get('video_codec', '').lower()
    audio_codec = video_info.get('audio_codec', '').lower()
    
    # H264 video dan AAC audio bisa langsung copy
    video_ok = video_codec in ['h264', 'avc']
    audio_ok = audio_codec in ['aac']
    
    logger.info(f"Video codec: {video_codec}, Audio codec: {audio_codec}")
    logger.info(f"Can use copy mode: video_ok={video_ok}, audio_ok={audio_ok}")
    
    return video_ok and audio_ok

def start_hls_conversion(input_path: str, output_path: str, stream_id: str) -> subprocess.Popen:
    """
    Start FFmpeg HLS conversion
    Menggunakan copy mode jika memungkinkan untuk minimal CPU usage
    """
    
    # Get video info
    video_info = get_video_info(input_path)
    use_copy = can_use_copy_mode(video_info) if config.USE_COPY_MODE else False
    
    # Check QSV availability
    has_qsv = check_qsv_available() if config.USE_QSV else False
    
    if use_copy:
        # COPY MODE - Ultra low CPU (1-3% per stream)
        logger.info(f"Using COPY mode for {stream_id} - minimal CPU usage")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",  # Loop infinitely
            "-i", input_path,
            "-c", "copy",  # Copy both video and audio
            "-f", "hls",
            "-hls_time", str(config.HLS_TIME),
            "-hls_list_size", str(config.HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+independent_segments",
            "-hls_segment_type", "mpegts",
            "-hls_playlist_type", "event",
            "-hls_segment_filename", os.path.join(output_path, "segment_%05d.ts"),
            os.path.join(output_path, "index.m3u8")
        ]
        
        mode = "copy"
        
    elif has_qsv:
        # HARDWARE ENCODING - Intel Quick Sync (low CPU)
        logger.info(f"Using Intel QSV hardware encoding for {stream_id}")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",
            "-hwaccel", "qsv",
            "-hwaccel_output_format", "qsv",
            "-i", input_path,
            "-c:v", "h264_qsv",
            "-preset", "veryfast",
            "-global_quality", "23",
            "-look_ahead", "0",
            "-b:v", config.VIDEO_MAXRATE,
            "-maxrate", config.VIDEO_MAXRATE,
            "-bufsize", "1600k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", config.AUDIO_CODEC,
            "-b:a", config.AUDIO_BITRATE,
            "-f", "hls",
            "-hls_time", str(config.HLS_TIME),
            "-hls_list_size", str(config.HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+independent_segments",
            "-hls_segment_type", "mpegts",
            "-hls_playlist_type", "event",
            "-hls_segment_filename", os.path.join(output_path, "segment_%05d.ts"),
            os.path.join(output_path, "index.m3u8")
        ]
        
        mode = "qsv"
        
    else:
        # SOFTWARE ENCODING - Fallback (higher CPU)
        logger.info(f"Using software encoding for {stream_id} - higher CPU usage")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1",
            "-i", input_path,
            "-c:v", config.VIDEO_CODEC,
            "-preset", config.VIDEO_PRESET,
            "-crf", config.VIDEO_CRF,
            "-maxrate", config.VIDEO_MAXRATE,
            "-bufsize", "1600k",
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "0",
            "-c:a", config.AUDIO_CODEC,
            "-b:a", config.AUDIO_BITRATE,
            "-f", "hls",
            "-hls_time", str(config.HLS_TIME),
            "-hls_list_size", str(config.HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+independent_segments",
            "-hls_segment_type", "mpegts",
            "-hls_playlist_type", "event",
            "-hls_segment_filename", os.path.join(output_path, "segment_%05d.ts"),
            os.path.join(output_path, "index.m3u8")
        ]
        
        mode = "software"
    
    logger.info(f"FFmpeg command: {' '.join(cmd)}")
    
    # Start process with lower priority untuk tidak ganggu system
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        preexec_fn=lambda: os.nice(5) if hasattr(os, 'nice') else None
    )
    
    # Store metadata
    stream_metadata[stream_id]['mode'] = mode
    stream_metadata[stream_id]['video_info'] = video_info
    
    return process

def sanitize_filename(filename: str) -> str:
    """Sanitize filename"""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = os.path.basename(filename)
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:95] + ext
    return filename

def validate_video_file(file: UploadFile) -> bool:
    """Validate uploaded file"""
    if not file.filename:
        return False
    file_ext = Path(file.filename).suffix.lower()
    return file_ext in config.ALLOWED_EXTENSIONS

async def cleanup_stream(stream_id: str):
    """Clean up stream process and files"""
    if stream_id in active_streams:
        process = active_streams[stream_id]
        try:
            process.terminate()
            await asyncio.sleep(2)
            if process.poll() is None:
                process.kill()
            logger.info(f"Terminated stream {stream_id}")
        except Exception as e:
            logger.error(f"Error terminating stream {stream_id}: {e}")
        finally:
            del active_streams[stream_id]
            if stream_id in stream_metadata:
                del stream_metadata[stream_id]

@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve control panel HTML"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VOD HLS Streamer - Intel J5005 Optimized</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                margin-bottom: 20px;
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 10px;
                font-size: 2em;
            }
            .subtitle {
                text-align: center;
                color: #666;
                margin-bottom: 30px;
                font-size: 0.9em;
            }
            h2 {
                color: #667eea;
                border-bottom: 3px solid #667eea;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }
            .info-box {
                background: #e3f2fd;
                border-left: 4px solid #2196F3;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }
            .warning-box {
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }
            .success-box {
                background: #d4edda;
                border-left: 4px solid #28a745;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
            }
            .form-group {
                margin: 20px 0;
            }
            label {
                display: block;
                margin-bottom: 8px;
                font-weight: bold;
                color: #333;
            }
            input[type="text"],
            input[type="file"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 14px;
                transition: border-color 0.3s;
            }
            input:focus {
                outline: none;
                border-color: #667eea;
            }
            .btn {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
                margin: 5px;
                transition: all 0.3s;
                display: inline-block;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            .btn-primary { background: #667eea; color: white; }
            .btn-danger { background: #dc3545; color: white; }
            .btn-warning { background: #ffc107; color: #333; }
            .btn-success { background: #28a745; color: white; }
            .btn-info { background: #17a2b8; color: white; }
            .stream-item {
                background: #f8f9fa;
                padding: 20px;
                margin: 15px 0;
                border-radius: 10px;
                border-left: 4px solid #28a745;
                transition: all 0.3s;
            }
            .stream-item:hover {
                box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                transform: translateX(5px);
            }
            .stream-url {
                background: #2c3e50;
                color: #ecf0f1;
                padding: 12px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                word-break: break-all;
                margin: 10px 0;
            }
            .badge {
                display: inline-block;
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 11px;
                font-weight: bold;
                margin: 0 5px;
            }
            .badge-copy { background: #28a745; color: white; }
            .badge-qsv { background: #007bff; color: white; }
            .badge-software { background: #ffc107; color: #333; }
            .controls {
                text-align: center;
                margin: 20px 0;
            }
            .status {
                margin: 20px 0;
                padding: 15px;
                border-radius: 8px;
                display: none;
            }
            .status.show { display: block; animation: slideIn 0.5s; }
            .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .status.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
                display: inline-block;
                margin-right: 10px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }
            .stat-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
            }
            .stat-value {
                font-size: 2em;
                font-weight: bold;
                margin: 10px 0;
            }
            .stat-label {
                font-size: 0.9em;
                opacity: 0.9;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            @keyframes slideIn {
                from { transform: translateY(-20px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎬 VOD HLS Streamer</h1>
            <div class="subtitle">Optimized for Intel Pentium J5005 - Ultra Low CPU Mode</div>
            
            <div class="success-box">
                <strong>✨ Copy Mode Aktif!</strong>
                <p>Video dengan codec H264+AAC akan di-stream tanpa transcoding = CPU usage minimal (1-3% per stream)</p>
            </div>
        </div>

        <div class="container">
            <h2>📊 System Stats</h2>
            <div class="stats-grid" id="statsGrid">
                <div class="stat-card">
                    <div class="stat-label">Active Streams</div>
                    <div class="stat-value" id="activeCount">0</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">CPU Usage</div>
                    <div class="stat-value" id="cpuUsage">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Memory Usage</div>
                    <div class="stat-value" id="memUsage">-</div>
                </div>
            </div>
        </div>

        <div class="container">
            <h2>📤 Upload Video</h2>
            <div class="info-box">
                <strong>ℹ️ Supported formats:</strong> MP4, AVI, MOV, MKV, WebM, FLV, TS<br>
                <strong>📏 Max file size:</strong> 500MB<br>
                <strong>⚡ Best performance:</strong> H264 video + AAC audio (akan otomatis gunakan copy mode)
            </div>
            
            <form id="uploadForm">
                <div class="form-group">
                    <label for="name">Stream Name:</label>
                    <input type="text" id="name" name="name" required placeholder="e.g., my_movie">
                </div>
                <div class="form-group">
                    <label for="file">Select Video File:</label>
                    <input type="file" id="file" name="file" accept="video/*" required>
                </div>
                <button type="submit" class="btn btn-primary">🚀 Upload & Start Stream</button>
            </form>
        </div>

        <div class="container">
            <h2>🎛️ Control Panel</h2>
            <div class="controls">
                <button onclick="refreshStreams()" class="btn btn-info">🔄 Refresh</button>
                <button onclick="refreshStats()" class="btn btn-info">📊 Update Stats</button>
                <button onclick="stopAllStreams()" class="btn btn-danger">⏹️ Stop All</button>
                <button onclick="cleanupAll()" class="btn btn-warning">🗑️ Cleanup All</button>
            </div>
        </div>

        <div class="container">
            <h2>📡 Active Streams</h2>
            <div id="streamsList">
                <div style="text-align: center; padding: 40px; color: #999;">
                    <div class="spinner"></div> Loading streams...
                </div>
            </div>
        </div>

        <div id="statusContainer"></div>

        <script>
            function showStatus(message, type = 'success') {
                const container = document.getElementById('statusContainer');
                container.innerHTML = `
                    <div class="container">
                        <div class="status ${type} show">${message}</div>
                    </div>
                `;
                setTimeout(() => {
                    const status = container.querySelector('.status');
                    if (status) status.classList.remove('show');
                }, 5000);
            }

            async function refreshStats() {
                try {
                    const response = await fetch('/stats');
                    const stats = await response.json();
                    
                    document.getElementById('activeCount').textContent = stats.active_streams;
                    document.getElementById('cpuUsage').textContent = stats.cpu_usage + '%';
                    document.getElementById('memUsage').textContent = stats.memory_usage + '%';
                } catch (error) {
                    console.error('Stats error:', error);
                }
            }

            async function refreshStreams() {
                try {
                    const response = await fetch('/streams');
                    const data = await response.json();
                    displayStreams(data);
                    refreshStats();
                } catch (error) {
                    showStatus('Failed to load streams: ' + error.message, 'error');
                }
            }

            function displayStreams(data) {
                const container = document.getElementById('streamsList');
                
                if (Object.keys(data).length === 0) {
                    container.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">No active streams</div>';
                    return;
                }
                
                let html = '';
                for (const [id, info] of Object.entries(data)) {
                    const modeBadge = info.mode === 'copy' ? 
                        '<span class="badge badge-copy">COPY MODE - Ultra Low CPU</span>' :
                        info.mode === 'qsv' ?
                        '<span class="badge badge-qsv">QSV Hardware</span>' :
                        '<span class="badge badge-software">Software Encode</span>';
                    
                    html += `
                        <div class="stream-item">
                            <h3>🎬 ${id} ${modeBadge}</h3>
                            <div class="stream-url">
                                <strong>HLS URL:</strong><br>
                                ${window.location.origin}${info.stream_url}
                            </div>
                            ${info.video_info ? `
                                <div style="margin: 10px 0; font-size: 0.9em; color: #666;">
                                    📹 ${info.video_info.width}x${info.video_info.height} | 
                                    🎥 ${info.video_info.video_codec} | 
                                    🔊 ${info.video_info.audio_codec} | 
                                    ⏱️ ${Math.round(info.video_info.duration)}s
                                </div>
                            ` : ''}
                            <div style="margin-top: 15px;">
                                <button onclick="copyUrl('${window.location.origin}${info.stream_url}')" class="btn btn-success">📋 Copy URL</button>
                                <button onclick="testStream('${info.stream_url}')" class="btn btn-primary">▶️ Test Stream</button>
                                <button onclick="stopStream('${id}')" class="btn btn-danger">⏹️ Stop</button>
                            </div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            }

            function copyUrl(url) {
                navigator.clipboard.writeText(url).then(() => {
                    showStatus('📋 URL copied to clipboard!', 'success');
                });
            }

            function testStream(url) {
                window.open(url, '_blank');
            }

            async function stopStream(id) {
                if (!confirm(`Stop stream: ${id}?`)) return;
                
                try {
                    const response = await fetch(`/streams/${id}`, { method: 'DELETE' });
                    if (response.ok) {
                        showStatus(`✅ Stream ${id} stopped`, 'success');
                        refreshStreams();
                    }
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }

            async function stopAllStreams() {
                if (!confirm('Stop ALL streams?')) return;
                
                try {
                    const response = await fetch('/streams/all', { method: 'DELETE' });
                    if (response.ok) {
                        showStatus('✅ All streams stopped', 'success');
                        refreshStreams();
                    }
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }

            async function cleanupAll() {
                if (!confirm('⚠️ Delete ALL files and streams?')) return;
                
                try {
                    const response = await fetch('/cleanup', { method: 'POST' });
                    if (response.ok) {
                        const result = await response.json();
                        showStatus('✅ Cleanup complete: ' + result.message, 'success');
                        refreshStreams();
                    }
                } catch (error) {
                    showStatus('Error: ' + error.message, 'error');
                }
            }

            document.getElementById('uploadForm').onsubmit = async (e) => {
                e.preventDefault();
                
                const formData = new FormData();
                formData.append('name', document.getElementById('name').value);
                formData.append('file', document.getElementById('file').files[0]);
                
                showStatus('📤 Uploading and processing... Please wait.', 'info');
                
                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        showStatus(`✅ Stream started! Mode: ${result.mode.toUpperCase()}`, 'success');
                        document.getElementById('uploadForm').reset();
                        setTimeout(refreshStreams, 2000);
                    } else {
                        showStatus(`❌ Error: ${result.detail}`, 'error');
                    }
                } catch (error) {
                    showStatus(`❌ Upload failed: ${error.message}`, 'error');
                }
            };

            // Auto-refresh
            refreshStreams();
            setInterval(refreshStreams, 15000);
            setInterval(refreshStats, 5000);
        </script>
    </body>
    </html>
    """

@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    file: UploadFile = File(...)
):
    """Handle video upload and start HLS streaming"""
    
    # Check concurrent streams limit
    if len(active_streams) >= config.MAX_CONCURRENT_STREAMS:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {config.MAX_CONCURRENT_STREAMS} streams reached. Stop some streams first."
        )
    
    try:
        if not name.strip():
            raise HTTPException(status_code=400, detail="Stream name required")
        
        if not validate_video_file(file):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}"
            )
        
        # Generate stream ID
        stream_id = f"{sanitize_filename(name)}_{uuid.uuid4().hex[:8]}"
        
        # Setup paths
        safe_filename = sanitize_filename(file.filename)
        input_path = Path(config.UPLOAD_FOLDER) / f"{stream_id}_{safe_filename}"
        output_path = Path(config.OUTPUT_FOLDER) / stream_id
        
        # Save file
        logger.info(f"Saving uploaded file to {input_path}")
        content = await file.read()
        
        if len(content) > config.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max {config.MAX_FILE_SIZE // (1024*1024)}MB"
            )
        
        with open(input_path, "wb") as f:
            f.write(content)
        
        # Cleanup existing stream if any
        if stream_id in active_streams:
            await cleanup_stream(stream_id)
        
        # Prepare output directory
        if output_path.exists():
            shutil.rmtree(output_path)
        output_path.mkdir(parents=True)
        
        # Initialize metadata
        stream_metadata[stream_id] = {
            "input_file": str(input_path),
            "output_dir": str(output_path),
            "started_at": datetime.now().isoformat(),
            "name": name
        }
        
        # Start conversion
        process = start_hls_conversion(str(input_path), str(output_path), stream_id)
        active_streams[stream_id] = process
        
        stream_url = f"/output/{stream_id}/index.m3u8"
        mode = stream_metadata[stream_id].get('mode', 'unknown')
        
        logger.info(f"Stream started: {stream_id} (mode: {mode})")
        
        return StreamResponse(
            stream_id=stream_id,
            stream_url=stream_url,
            status="streaming",
            mode=mode
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/streams")
async def list_streams():
    """List all active streams with metadata"""
    streams = {}
    dead_streams = []
    
    for stream_id, process in active_streams.items():
        if process.poll() is None:  # Still running
            streams[stream_id] = {
                "stream_url": f"/output/{stream_id}/index.m3u8",
                "mode": stream_metadata.get(stream_id, {}).get('mode', 'unknown'),
                "video_info": stream_metadata.get(stream_id, {}).get('video_info', {}),
                "started_at": stream_metadata.get(stream_id, {}).get('started_at', '')
            }
        else:
            dead_streams.append(stream_id)
    
    # Cleanup dead streams
    for stream_id in dead_streams:
        await cleanup_stream(stream_id)
    
    return streams

@app.delete("/streams/{stream_id}")
async def stop_stream(stream_id: str):
    """Stop specific stream"""
    if stream_id not in active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    await cleanup_stream(stream_id)
    
    # Remove output directory
    output_path = Path(config.OUTPUT_FOLDER) / stream_id
    if output_path.exists():
        shutil.rmtree(output_path)
    
    return {"message": f"Stream {stream_id} stopped"}

@app.delete("/streams/all")
async def stop_all_streams():
    """Stop all active streams"""
    stopped = []
    
    for stream_id in list(active_streams.keys()):
        await cleanup_stream(stream_id)
        
        output_path = Path(config.OUTPUT_FOLDER) / stream_id
        if output_path.exists():
            shutil.rmtree(output_path)
        
        stopped.append(stream_id)
    
    return {"message": f"Stopped {len(stopped)} streams", "streams": stopped}

@app.post("/cleanup")
async def cleanup_all():
    """Cleanup all files and streams"""
    try:
        # Stop all streams
        for stream_id in list(active_streams.keys()):
            await cleanup_stream(stream_id)
        
        # Clean uploads
        upload_count = 0
        if os.path.exists(config.UPLOAD_FOLDER):
            for f in os.listdir(config.UPLOAD_FOLDER):
                f_path = os.path.join(config.UPLOAD_FOLDER, f)
                if os.path.isfile(f_path):
                    os.remove(f_path)
                    upload_count += 1
        
        # Clean outputs
        output_count = 0
        if os.path.exists(config.OUTPUT_FOLDER):
            for d in os.listdir(config.OUTPUT_FOLDER):
                d_path = os.path.join(config.OUTPUT_FOLDER, d)
                if os.path.isdir(d_path):
                    shutil.rmtree(d_path)
                    output_count += 1
        
        message = f"Removed {upload_count} uploads, {output_count} stream directories"
        logger.info(message)
        
        return {"message": message}
    
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    """Get system statistics"""
    return {
        "cpu_usage": round(psutil.cpu_percent(interval=0.5), 1),
        "memory_usage": round(psutil.virtual_memory().percent, 1),
        "active_streams": len(active_streams),
        "max_streams": config.MAX_CONCURRENT_STREAMS
    }

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("Shutting down, cleaning up streams...")
    for stream_id in list(active_streams.keys()):
        await cleanup_stream(stream_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
