# TubeStream Pro 🚀 — Modern YouTube Video & Playlist Downloader

A full-stack, responsive web application for downloading YouTube videos and playlists in **1080p Full HD MP4** or **320kbps Studio-Quality MP3** with real-time **Server-Sent Events (SSE)** progress streaming and an automated background file cleanup engine.

---

## 🌟 Features & Highlights

- **⚡ Live Real-Time Stream**: Real-time progress updates via Server-Sent Events (SSE) streaming download percentage, download speed (MB/s), ETA timer, and total bytes.
- **🎥 Full HD MP4 Video**: Automatic merging of high-bitrate video and audio streams using FFmpeg.
- **🎵 High-Fidelity 320kbps MP3**: Studio audio extraction with embedded ID3 metadata and tags.
- **📑 YouTube Playlist Batch Support**: Download entire playlists or select specific tracks, automatically packaged into a single `.zip` archive.
- **🛡️ Auto-Cleanup Routine**: Automatic background worker deletes temporary server media after user downloads complete or when files exceed retention limits (20 minutes).
- **💎 Glassmorphism UI**: Minimalist cyber-dark aesthetic built with Tailwind CSS, custom glow shaders, and smooth micro-interactions.
- **🔄 Universal Compatibility**: Standalone FFmpeg bundling via `imageio-ffmpeg` or system PATH detection.

---

## 📁 Project Structure

```text
yt-downloader-app/
├── app.py                     # FastAPI backend application & API routes
├── downloader.py              # yt-dlp core wrapper, format resolver & progress hook
├── cleaner.py                 # Background file auto-cleanup and storage monitor
├── requirements.txt           # Python dependencies
├── templates/
│   └── index.html             # Responsive HTML5 & Tailwind CSS UI
├── static/
│   ├── css/
│   │   └── style.css          # Glassmorphism styling, glows & animations
│   └── js/
│       └── app.js             # SSE stream consumer, DOM state & playlist controls
└── README.md                  # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** (Python 3.12 recommended)
- **Pip** (Python package installer)

### 2. Installation

Navigate to the project directory and install the required dependencies:

```bash
cd C:\Users\pawan\.gemini\antigravity-ide\scratch\yt-downloader-app
pip install -r requirements.txt
```

*(Note: `imageio-ffmpeg` will automatically supply an embedded FFmpeg binary for Windows/Linux/macOS if system FFmpeg is not installed).*

### 3. Running the Application

Launch the FastAPI development server with Uvicorn:

```bash
python app.py
```
*or directly with Uvicorn:*
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:8000`**

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web Application UI |
| `GET` | `/api/health` | Service & FFmpeg status check |
| `POST` | `/api/metadata` | Extract video/playlist title, thumbnail, qualities & tracks |
| `POST` | `/api/download` | Queue background download task, returns `task_id` |
| `GET` | `/api/progress/{task_id}` | Real-time Server-Sent Events (SSE) progress stream |
| `GET` | `/api/status/{task_id}` | Polling fallback for task progress & state |
| `GET` | `/api/download/{task_id}` | Stream file download to browser & trigger auto-cleanup |
| `POST` | `/api/cancel/{task_id}` | Cancel an ongoing download task |

---

## 🔒 Storage & Auto-Cleanup Architecture

To guarantee the server never runs out of disk storage:
1. **Response-Triggered Cleanup**: When a user triggers `/api/download/{task_id}`, a background task schedules safe removal of the temporary directory after 120 seconds.
2. **Periodic Daemon Sweeper**: An automated background loop runs every 5 minutes and purges any file or directory older than 20 minutes.
