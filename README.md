# 🎬 VOD HLS Streamer - Optimized for Intel Pentium J5005

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg)](https://fastapi.tiangolo.com)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-4.x-green.svg)](https://ffmpeg.org)
[![License](https://img.shields.io/badge/license-MIT-red.svg)](LICENSE)

**VOD HLS Streamer** adalah aplikasi web server ringan untuk mengubah video menjadi streaming HLS (HTTP Live Streaming) dengan konsumsi CPU yang sangat rendah. Aplikasi ini **khusus dioptimalkan** untuk perangkat dengan spesifikasi terbatas seperti **Intel Pentium J5005**.

## ✨ Fitur Utama

| Fitur | Deskripsi |
|-------|------------|
| 🎬 **Upload Video** | Upload berbagai format (MP4, AVI, MKV, WebM, FLV, TS) max 500MB |
| 🔄 **Copy Mode** | Mode tanpa transcoding untuk video H264+AAC (CPU usage **1-3%** per stream) |
| 🚀 **Hardware Acceleration** | Dukungan penuh Intel Quick Sync Video (QSV) |
| 📡 **HLS Streaming** | Output standar HLS (.m3u8 playlist + .ts segments) |
| 🎛️ **Web Control Panel** | Dashboard lengkap untuk manage semua streams |
| 📊 **Real-time Monitoring** | Monitoring CPU, Memory, dan Active Streams |
| 🗑️ **One-click Cleanup** | Hapus semua file dan streams dengan satu klik |

## 📊 Performance Benchmark (Intel J5005)

| Mode | 1 Stream 480p | 1 Stream 720p | 5 Streams 480p | 10 Streams 480p |
|------|--------------|--------------|----------------|-----------------|
| **Copy Mode** | 2% CPU | 3% CPU | 10% CPU | 20% CPU |
| QSV Hardware | 15% CPU | 20% CPU | - | - |
| Software Encode | 45% CPU | 60% CPU | - | - |

> 💡 **Copy Mode** hanya bekerja untuk video dengan codec **H264 + AAC** (format paling umum)

## 🖥️ Demo

### Web Interface
![Web Interface](https://via.placeholder.com/800x400?text=Web+Control+Panel)

### Streaming Player
![HLS Player](https://via.placeholder.com/800x400?text=HLS+Streaming+Player)

## 📋 Persyaratan Sistem

### Minimum Requirements
```yaml
CPU: Intel Pentium J5005 atau lebih tinggi (x86_64)
RAM: 2 GB (4 GB direkomendasikan)
Storage: 10 GB (tergantung jumlah video)
OS: Ubuntu 20.04+ / Debian 11+ / Linux Mint 20+
