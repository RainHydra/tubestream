import os
import re
import sys
import shutil
import zipfile
import threading
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import yt_dlp

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Try to find FFmpeg path
FFMPEG_EXE: Optional[str] = None

def get_ffmpeg_path() -> Optional[str]:
    """Detects FFmpeg executable from system PATH or imageio_ffmpeg bundled binary."""
    global FFMPEG_EXE
    if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
        return FFMPEG_EXE
    
    # 1. Check system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        FFMPEG_EXE = system_ffmpeg
        logger.info(f"Using system FFmpeg at: {FFMPEG_EXE}")
        return FFMPEG_EXE
    
    # 2. Check imageio-ffmpeg bundled binary
    try:
        import imageio_ffmpeg
        bundled_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_exe and os.path.exists(bundled_exe):
            FFMPEG_EXE = bundled_exe
            logger.info(f"Using imageio-ffmpeg at: {FFMPEG_EXE}")
            return FFMPEG_EXE
    except Exception as e:
        logger.debug(f"imageio_ffmpeg not available: {e}")
        
    logger.warning("No FFmpeg found. Audio/video merging or MP3 conversion may be limited to native formats.")
    return None

def format_bytes(size: Optional[int]) -> str:
    """Formats raw bytes into human readable string (KB, MB, GB)."""
    if not size or size <= 0:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def format_duration(seconds: Optional[int]) -> str:
    """Formats seconds into HH:MM:SS or MM:SS."""
    if not seconds or seconds < 0:
        return "--:--"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def sanitize_filename(title: str) -> str:
    """Removes invalid filename characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return clean.strip()[:150] or "youtube_download"


class DownloadTaskManager:
    """Manages active, running, completed, and failed download tasks."""
    def __init__(self, downloads_dir: Path):
        self.downloads_dir = downloads_dir
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def create_task(self, task_id: str, title: str = "Initializing...") -> Dict[str, Any]:
        with self.lock:
            task = {
                "task_id": task_id,
                "title": title,
                "status": "initializing",  # initializing, fetching, downloading, processing, completed, error, cancelled
                "percent": 0.0,
                "speed_str": "0 KB/s",
                "eta_str": "--:--",
                "downloaded_bytes_str": "0 MB",
                "total_bytes_str": "0 MB",
                "current_item": 1,
                "total_items": 1,
                "filename": None,
                "file_path": None,
                "file_size": 0,
                "file_size_str": "0 MB",
                "error_message": None,
                "is_cancelled": False,
                "download_url": None,
                "created_at": None,
                "completed_at": None,
            }
            self.tasks[task_id] = task
            return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)

    def cancel_task(self, task_id: str) -> bool:
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["is_cancelled"] = True
                self.tasks[task_id]["status"] = "cancelled"
                return True
            return False

    def remove_task(self, task_id: str):
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]


def extract_media_metadata(url: str, is_playlist: bool = False) -> Dict[str, Any]:
    """
    Extracts metadata from YouTube URL for single video or playlist without downloading.
    """
    ffmpeg_path = get_ffmpeg_path()
    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist" if is_playlist else False,
    }
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"Error extracting metadata for {url}: {e}")
            raise ValueError(f"Failed to fetch metadata: {str(e)}")

    if not info:
        raise ValueError("Could not retrieve information for this URL.")

    # Determine if it's a playlist or single video
    is_playlist_result = "entries" in info

    if is_playlist_result and is_playlist:
        raw_entries = list(info.get("entries") or [])
        entries = []
        for idx, entry in enumerate(raw_entries[:50]):  # Limit playlist view to first 50 items for snappy performance
            if entry:
                entries.append({
                    "index": idx + 1,
                    "id": entry.get("id"),
                    "title": entry.get("title") or f"Track {idx + 1}",
                    "duration": entry.get("duration"),
                    "duration_formatted": format_duration(entry.get("duration")),
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    "thumbnail": entry.get("thumbnails", [{}])[-1].get("url") if entry.get("thumbnails") else None,
                    "uploader": entry.get("uploader") or entry.get("channel") or "Unknown Artist",
                })

        return {
            "is_playlist": True,
            "id": info.get("id"),
            "title": info.get("title") or "YouTube Playlist",
            "uploader": info.get("uploader") or info.get("channel") or "YouTube",
            "thumbnail": info.get("thumbnails", [{}])[-1].get("url") if info.get("thumbnails") else (entries[0]["thumbnail"] if entries else None),
            "video_count": len(raw_entries),
            "entries": entries,
            "has_ffmpeg": bool(ffmpeg_path)
        }
    else:
        # Single Video (or first item of playlist if user asked for single)
        if "entries" in info:
            entries = list(info.get("entries") or [])
            if not entries or not entries[0]:
                raise ValueError("Playlist contains no playable videos.")
            info = entries[0]

        # Parse available formats
        formats = info.get("formats", [])
        video_qualities = {}
        audio_qualities = []

        # Available standard heights we want to present
        target_heights = [2160, 1440, 1080, 720, 480, 360, 240, 144]

        # Scan formats for best representations
        for f in formats:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            height = f.get("height")
            ext = f.get("ext")
            filesize = f.get("filesize") or f.get("filesize_approx")

            # Video format
            if vcodec != "none" and height:
                for th in target_heights:
                    if height == th or (height >= th and th not in video_qualities):
                        label = f"{th}p"
                        fps = f.get("fps")
                        if fps and fps >= 50:
                            label += f" {fps}fps"
                        
                        if th not in video_qualities or (f.get("tbr") or 0) > (video_qualities[th].get("tbr") or 0):
                            video_qualities[th] = {
                                "quality": f"{th}p",
                                "height": th,
                                "label": label,
                                "ext": "mp4",
                                "filesize": filesize,
                                "filesize_formatted": format_bytes(filesize) if filesize else "Adaptive Size",
                                "tbr": f.get("tbr", 0),
                                "format_id": f.get("format_id"),
                                "has_audio": acodec != "none",
                            }

        # Build clean sorted video options list
        sorted_video_options = []
        for th in sorted(video_qualities.keys(), reverse=True):
            sorted_video_options.append(video_qualities[th])

        if not sorted_video_options:
            sorted_video_options.append({
                "quality": "best",
                "height": 720,
                "label": "Best Quality Available (MP4)",
                "ext": "mp4",
                "filesize_formatted": "Auto",
                "has_audio": True
            })

        # Audio options
        audio_options = [
            {"quality": "320k", "label": "MP3 - 320 kbps (Studio Quality)", "ext": "mp3", "bitrate": "320k"},
            {"quality": "256k", "label": "MP3 - 256 kbps (High Quality)", "ext": "mp3", "bitrate": "256k"},
            {"quality": "128k", "label": "MP3 - 128 kbps (Standard)", "ext": "mp3", "bitrate": "128k"},
            {"quality": "m4a", "label": "M4A / AAC (Original Audio Stream)", "ext": "m4a", "bitrate": "best"},
        ]

        duration = info.get("duration")
        view_count = info.get("view_count")
        view_str = f"{view_count:,}" if view_count else "N/A"

        return {
            "is_playlist": False,
            "id": info.get("id"),
            "title": info.get("title") or "YouTube Video",
            "uploader": info.get("uploader") or info.get("channel") or "Unknown Creator",
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "thumbnail": info.get("thumbnail") or (info.get("thumbnails", [{}])[-1].get("url") if info.get("thumbnails") else None),
            "view_count": view_str,
            "upload_date": info.get("upload_date"),
            "description": (info.get("description") or "")[:250],
            "video_options": sorted_video_options,
            "audio_options": audio_options,
            "has_ffmpeg": bool(ffmpeg_path)
        }


def execute_download(
    task_manager: DownloadTaskManager,
    task_id: str,
    url: str,
    format_type: str,       # 'video' or 'audio'
    quality: str,           # '1080p', '720p', 'best', '320k', '256k', etc.
    is_playlist: bool = False,
    selected_indices: Optional[List[int]] = None
):
    """
    Background download executor with real-time progress callbacks.
    """
    task = task_manager.get_task(task_id)
    if not task:
        return

    ffmpeg_path = get_ffmpeg_path()
    task_manager.update_task(task_id, status="fetching", percent=5.0)

    # Progress hook for yt-dlp
    def ydl_progress_hook(d: Dict[str, Any]):
        if task_manager.get_task(task_id).get("is_cancelled"):
            raise Exception("Download cancelled by user.")

        status = d.get("status")
        if status == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded_bytes = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0

            percent = 0.0
            if total_bytes > 0:
                percent = round((downloaded_bytes / total_bytes) * 90.0, 1)  # Scale to 90% to leave room for post-processing
            elif "_percent_str" in d:
                raw_pct = re.sub(r"[^\d.]", "", d["_percent_str"])
                try:
                    percent = round(float(raw_pct) * 0.9, 1)
                except ValueError:
                    percent = 50.0

            speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed > 1024 * 1024 else f"{speed / 1024:.1f} KB/s" if speed > 0 else "Calculating..."
            eta_str = f"{int(eta)}s" if eta and eta < 60 else f"{int(eta // 60)}m {int(eta % 60)}s" if eta else "--:--"

            task_manager.update_task(
                task_id,
                status="downloading",
                percent=max(5.0, min(95.0, percent)),
                speed_str=speed_str,
                eta_str=eta_str,
                downloaded_bytes_str=format_bytes(downloaded_bytes),
                total_bytes_str=format_bytes(total_bytes) if total_bytes > 0 else "Calculating..."
            )
        elif status == "finished":
            task_manager.update_task(
                task_id,
                status="processing",
                percent=92.0,
                speed_str="Finalizing...",
                eta_str="Moments away"
            )

    # Postprocessor hook
    def ydl_postprocessor_hook(d: Dict[str, Any]):
        status = d.get("status")
        postprocessor = d.get("postprocessor")
        if status == "started":
            task_manager.update_task(
                task_id,
                status="processing",
                percent=95.0,
                speed_str=f"Running {postprocessor or 'FFmpeg'}",
                eta_str="Finalizing"
            )

    try:
        # Prepare output template
        task_out_dir = task_manager.downloads_dir / task_id
        task_out_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts: Dict[str, Any] = {
            "progress_hooks": [ydl_progress_hook],
            "postprocessor_hooks": [ydl_postprocessor_hook],
            "no_warnings": True,
            "quiet": True,
            "ignoreerrors": True if is_playlist else False,
            "nocheckcertificate": True,
        }

        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        # Playlist specific options
        if is_playlist:
            ydl_opts["outtmpl"] = str(task_out_dir / "%(playlist_index)s - %(title)s.%(ext)s")
            if selected_indices:
                # 1-indexed playlist items
                ydl_opts["playlist_items"] = ",".join(str(i) for i in selected_indices)
        else:
            ydl_opts["outtmpl"] = str(task_out_dir / "%(title)s.%(ext)s")
            ydl_opts["noplaylist"] = True

        # Build format / postprocessor selector
        if format_type == "audio":
            if ffmpeg_path:
                preferred_codec = "mp3" if "mp3" in quality or quality in ["320k", "256k", "128k"] else "m4a"
                preferred_bitrate = "320" if quality == "320k" else "256" if quality == "256k" else "128"
                
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": preferred_codec,
                        "preferredquality": preferred_bitrate,
                    },
                    {
                        "key": "FFmpegMetadata",
                        "add_metadata": True,
                    }
                ]
            else:
                # FFmpeg missing fallback: grab native m4a or best audio
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        else:
            # Video Format selection
            if "p" in quality:
                height_match = re.search(r"(\d+)p", quality)
                target_height = int(height_match.group(1)) if height_match else 720
            else:
                target_height = 1080

            if ffmpeg_path:
                # Merge best video matching resolution with best audio
                ydl_opts["format"] = (
                    f"bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={target_height}]+bestaudio/"
                    f"best[height<={target_height}][ext=mp4]/best[height<={target_height}]/best"
                )
                ydl_opts["merge_output_format"] = "mp4"
            else:
                # Fallback: Best pre-merged MP4 format that doesn't strictly need FFmpeg
                ydl_opts["format"] = f"best[height<={target_height}][ext=mp4]/best[ext=mp4]/best"

        # Execute yt-dlp download
        logger.info(f"Starting download task {task_id} for URL: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_info = ydl.extract_info(url, download=True)

        # Inspect downloaded output
        downloaded_files = list(task_out_dir.glob("*.*"))
        # Filter out intermediate temporary files (.part, .ytdl, etc.)
        valid_files = [f for f in downloaded_files if not f.name.endswith((".part", ".ytdl", ".temp"))]

        if not valid_files:
            raise FileNotFoundError("No output media files were generated. The video might be restricted or unavailable.")

        if is_playlist and len(valid_files) > 1:
            # Zip all playlist files into a single archive
            playlist_title = sanitize_filename(download_info.get("title") or "YouTube_Playlist")
            zip_filename = f"{playlist_title}.zip"
            zip_path = task_out_dir / zip_filename

            task_manager.update_task(task_id, status="processing", speed_str="Zipping playlist...", eta_str="Almost done")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_entry in valid_files:
                    if file_entry != zip_path:
                        zip_file.write(file_entry, arcname=file_entry.name)

            final_file = zip_path
            final_filename = zip_filename
        else:
            final_file = valid_files[0]
            final_filename = final_file.name

        file_size = final_file.stat().st_size
        file_size_str = format_bytes(file_size)

        task_manager.update_task(
            task_id,
            status="completed",
            percent=100.0,
            speed_str="Finished",
            eta_str="0s",
            filename=final_filename,
            file_path=str(final_file),
            file_size=file_size,
            file_size_str=file_size_str,
            download_url=f"/api/download/{task_id}",
        )
        logger.info(f"Task {task_id} completed successfully: {final_filename} ({file_size_str})")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Task {task_id} failed: {error_msg}")
        task_manager.update_task(
            task_id,
            status="error",
            error_message=error_msg,
            percent=0.0
        )
