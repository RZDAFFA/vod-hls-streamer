# 🎬 VOD HLS Streamer - Optimized for Intel Pentium J5005

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg)](https://fastapi.tiangolo.com)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-4.x-green.svg)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/license-MIT-red.svg)](LICENSE)

**VOD HLS Streamer** adalah aplikasi web server ringan untuk mengubah video menjadi streaming HLS (HTTP Live Streaming) dengan konsumsi CPU yang sangat rendah. Aplikasi ini **khusus dioptimalkan** untuk perangkat dengan spesifikasi terbatas seperti **Intel Pentium J5005**.

---

## 📋 Daftar Isi

- [✨ Fitur Utama](#-fitur-utama)
- [📊 Performance Benchmark](#-performance-benchmark-intel-j5005)
- [📋 Persyaratan Sistem](#-persyaratan-sistem)
- [🚀 Instalasi](#-instalasi)
- [📁 Struktur Project](#-struktur-project)
- [⚙️ Konfigurasi](#-konfigurasi)
- [📡 API Endpoints](#-api-endpoints)
- [🎮 Cara Penggunaan](#-cara-penggunaan)
- [🔧 Troubleshooting](#-troubleshooting)
- [🏗️ Arsitektur Sistem](#-arsitektur-sistem)
- [🚀 Deployment](#-deployment)
- [🤝 Kontribusi](#-kontribusi)
- [📝 Changelog](#-changelog)
- [📄 Lisensi](#-lisensi)

---

## ✨ Fitur Utama

| Fitur | Deskripsi |
| :--- | :--- |
| 🎬 **Upload Video** | Upload berbagai format (MP4, AVI, MKV, WebM, FLV, TS) max 500MB |
| 🔄 **Copy Mode** | Mode tanpa transcoding untuk video H264+AAC (**CPU usage 1-3%** per stream) |
| 🚀 **Hardware Acceleration** | Dukungan penuh Intel Quick Sync Video (QSV) |
| 📡 **HLS Streaming** | Output standar HLS (`.m3u8` playlist + `.ts` segments) |
| 🎛️ **Web Control Panel** | Dashboard lengkap untuk manage semua streams |
| 📊 **Real-time Monitoring** | Monitoring CPU, Memory, dan Active Streams |
| 🗑️ **One-click Cleanup** | Hapus semua file dan streams dengan satu klik |

---

## 📊 Performance Benchmark (Intel J5005)

| Mode | 1 Stream (480p) | 1 Stream (720p) | 5 Streams (480p) | 10 Streams (480p) |
| :--- | :---: | :---: | :---: | :---: |
| **Copy Mode** | 2% CPU | 3% CPU | 10% CPU | 20% CPU |
| QSV Hardware | 15% CPU | 20% CPU | 35% CPU | - |
| Software Encode | 45% CPU | 60% CPU | - | - |

> 💡 **Copy Mode** hanya bekerja untuk video dengan codec **H264 + AAC** (format paling umum)

---

## 📋 Persyaratan Sistem

### Minimum Requirements

```yaml
CPU: Intel Pentium J5005 atau lebih tinggi (x86_64)
RAM: 2 GB (4 GB direkomendasikan)
Storage: 10 GB (tergantung jumlah video)
OS: Ubuntu 20.04+ / Debian 11+ / Linux Mint 20+
```

### Software Dependencies

| Software | Version | Keterangan |
| :--- | :---: | :--- |
| Python | 3.8+ | Wajib |
| FFmpeg | 4.x | Wajib |
| pip3 | latest | Wajib |
| Intel Media Driver | latest | Opsional (untuk QSV) |

---

## 🚀 Instalasi

### Step-by-step Installation

1.  **Update system dan install dependencies:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install python3 python3-pip ffmpeg -y
    sudo apt install intel-media-va-driver-non-free vainfo -y # Opsional untuk QSV
    ```

2.  **Clone repository:**
    ```bash
    git clone https://github.com/RZDAFFA/vod-hls-streamer.git
    cd vod-hls-streamer
    ```

3.  **Install Python packages:**
    ```bash
    pip3 install -r requirements.txt
    ```

4.  **Buat folder yang diperlukan:**
    ```bash
    mkdir -p uploads output
    ```

5.  **Jalankan aplikasi:**
    ```bash
    python3 main.py
    # atau dengan uvicorn
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```

### Akses Web Interface

Buka browser dan akses:
```
http://localhost:8000
```

---

## 📁 Struktur Project

```
vod-hls-streamer/
├── main.py                 # Aplikasi utama FastAPI
├── requirements.txt        # Python dependencies
├── README.md               # Dokumentasi
├── run.sh                  # Script untuk menjalankan server
├── uploads/                # Folder untuk file upload (auto-generated)
└── output/                 # Folder untuk HLS segments (auto-generated)
    └── [stream_id]/
        ├── index.m3u8      # HLS playlist
        └── segment_*.ts    # Segmen video
```

---

## ⚙️ Konfigurasi

Edit parameter di `main.py` pada bagian `class Config`:

```python
class Config:
    # ========== FILE SYSTEM ==========
    UPLOAD_FOLDER = "uploads"
    OUTPUT_FOLDER = "output"
    MAX_FILE_SIZE = 500 * 1024 * 1024      # 500MB
    ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".ts"}
    
    # ========== HLS SETTINGS ==========
    HLS_TIME = 6                    # Durasi per segment (detik)
    HLS_LIST_SIZE = 5               # Jumlah segment dalam playlist
    
    # ========== COPY MODE (PENTING!) ==========
    USE_COPY_MODE = True            # True = minimal CPU usage (1-3%)
                                    # False = transcoding (40-60% CPU)
    
    # ========== FALLBACK TRANSCODING ==========
    VIDEO_CODEC = "libx264"
    VIDEO_PRESET = "ultrafast"
    VIDEO_CRF = "28"
    VIDEO_MAXRATE = "800k"
    AUDIO_CODEC = "aac"
    AUDIO_BITRATE = "96k"
    
    # ========== HARDWARE ACCELERATION ==========
    USE_QSV = True                  # Gunakan Intel Quick Sync jika tersedia
    
    # ========== CONCURRENCY ==========
    MAX_CONCURRENT_STREAMS = 10     # Maksimal stream bersamaan
```

---

## 📡 API Endpoints

| Method | Endpoint | Deskripsi |
| :--- | :--- | :--- |
| GET | `/` | Web control panel |
| POST | `/upload` | Upload video & start stream |
| GET | `/streams` | List semua active streams |
| DELETE | `/streams/{id}` | Stop specific stream |
| DELETE | `/streams/all` | Stop semua streams |
| POST | `/cleanup` | Hapus semua file |
| GET | `/stats` | System statistics |

### Contoh API Call

**Upload video:**
```bash
curl -X POST http://localhost:8000/upload \
  -F "name=my_video" \
  -F "file=@/path/to/video.mp4"
```

**Response:**
```json
{
  "stream_id": "my_video_a1b2c3d4",
  "stream_url": "/output/my_video_a1b2c3d4/index.m3u8",
  "status": "streaming",
  "mode": "copy"
}
```

---

## 🎮 Cara Penggunaan

### 1. Upload Video via Web
- Buka browser di `http://localhost:8000`
- Isi **Stream Name** (contoh: `movie_1`)
- Pilih file video (max 500MB)
- Klik **Upload & Start Stream**

### 2. Dapatkan URL Streaming
Setelah upload selesai, akan muncul URL seperti:
```
http://localhost:8000/output/movie_1_a1b2c3d4/index.m3u8
```

### 3. Putar Stream

**Menggunakan VLC Player:**
1. Buka VLC Player
2. `Media` → `Open Network Stream` (`Ctrl+N`)
3. Paste URL `.m3u8` dan klik `Play`

**Menggunakan HTML5 + hls.js:**
```html
<video id="video" controls></video>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
    const video = document.getElementById('video');
    const streamUrl = 'http://localhost:8000/output/stream_id/index.m3u8';
    
    if (Hls.isSupported()) {
        const hls = new Hls();
        hls.loadSource(streamUrl);
        hls.attachMedia(video);
    }
</script>
```

---

## 🔧 Troubleshooting

### ❌ Error: FFmpeg not found
```bash
sudo apt install ffmpeg -y
which ffmpeg
```

### ❌ Error: Port 8000 already in use
```bash
lsof -i :8000
kill -9 [PID]
```

### ❌ CPU usage tinggi terus
**Penyebab:** `USE_COPY_MODE = False` atau video tidak berformat H264+AAC.

**Solusi:**
```bash
# Cek codec video
ffprobe -v error -show_entries stream=codec_name video.mp4

# Konversi jika perlu
ffmpeg -i input.mp4 -c:v libx264 -c:a aac output.mp4
```

---

## 🏗️ Arsitektur Sistem

```
[ CLIENT ]  -->  [ FASTAPI SERVER ]  -->  [ FFmpeg PROCESS ]  -->  [ FILE SYSTEM ]
(Browser/VLC)    (Web UI, API)          (Copy/QSV/Software)     (uploads/, output/)
```

### Mode Operasi

| Mode | Trigger | CPU Usage | Kualitas |
| :--- | :--- | :--- | :--- |
| **Copy Mode** | Video H264 + AAC | 1-3% | Original |
| QSV Hardware | Intel QSV available | 10-20% | Good |
| Software Encode | Fallback | 40-60% | Acceptable |

---

## 🚀 Deployment

### Systemd Service (Auto-start) - RECOMMENDED

Buat file `/etc/systemd/system/vod-streamer.service`:

```ini
[Unit]
Description=VOD HLS Streamer for Intel J5005
After=network.target

[Service]
Type=simple
User=badrus
WorkingDirectory=/home/badrus/VOD
ExecStart=/usr/local/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
Nice=10

[Install]
WantedBy=multi-user.target
```

Kemudian:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vod-streamer
sudo systemctl start vod-streamer
```

---

## 🤝 Kontribusi

Kontribusi selalu diterima! Silakan:

1. Fork repository
2. Buat branch fitur (`git checkout -b feature/AmazingFeature`)
3. Commit perubahan (`git commit -m 'Add some AmazingFeature'`)
4. Push ke branch (`git push origin feature/AmazingFeature`)
5. Buat Pull Request

---

## 📝 Changelog

### [1.0.0] - 2026-04-23

**Initial Release:**
- ✅ Copy mode untuk video H264+AAC (CPU usage 1-3%)
- ✅ Dukungan Intel Quick Sync Video (QSV)
- ✅ Web control panel lengkap
- ✅ Real-time system monitoring
- ✅ REST API endpoints

---

## 📄 Lisensi

Distributed under the MIT License.

```
MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy...
```

---

## 🙏 Credits

- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [FFmpeg](https://ffmpeg.org/) - Video processing
- [Intel](https://www.intel.com/content/www/us/en/architecture-and-technology/quick-sync-video/quick-sync-video-general.html) - Quick Sync Video

---

**Made with ❤️ for Intel Pentium J5005 users**
