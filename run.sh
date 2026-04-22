#!/bin/bash

# Script untuk menjalankan VOD HLS Streamer

echo "========================================="
echo "🎬 VOD HLS Streamer - Intel J5005 Optimized"
echo "========================================="
echo ""

# Cek apakah FFmpeg terinstall
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg not found! Installing..."
    sudo apt install ffmpeg -y
fi

# Cek apakah Python packages terinstall
if ! pip3 list | grep -q fastapi; then
    echo "📦 Installing Python dependencies..."
    pip3 install fastapi uvicorn python-multipart psutil
fi

# Buat folder jika belum ada
mkdir -p uploads output

echo "✅ Starting server..."
echo "🌐 Access at: http://localhost:8000"
echo "========================================="
echo ""

# Jalankan server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
