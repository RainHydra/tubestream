import os
import sys
import uuid
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from downloader import (
    DownloadTaskManager,
    extract_media_metadata,
    execute_download,
    get_ffmpeg_path,
)
from cleaner import AutoCleanupService

# Setup base paths
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yt_downloader")

# Core services
task_manager = DownloadTaskManager(downloads_dir=DOWNLOADS_DIR)
cleanup_service = AutoCleanupService(downloads_dir=DOWNLOADS_DIR, task_manager=task_manager, interval_seconds=300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start cleanup worker
    cleanup_task = asyncio.create_task(cleanup_service.start())
    ffmpeg_detected = get_ffmpeg_path()
    logger.info(f"App initialized. FFmpeg available: {bool(ffmpeg_detected)} ({ffmpeg_detected})")
    yield
    # Shutdown
    cleanup_service.stop()
    cleanup_task.cancel()

# Initialize FastAPI application
app = FastAPI(
    title="TubeStream Pro - High-Speed YouTube Media Downloader",
    description="Full-stack responsive YouTube Video & Playlist Downloader with real-time SSE progress updates.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ------------------ Request Models ------------------
class MetadataRequest(BaseModel):
    url: str
    is_playlist: bool = False

class DownloadRequest(BaseModel):
    url: str
    format_type: str = "video"  # "video" or "audio"
    quality: str = "1080p"      # "1080p", "720p", "320k", etc.
    is_playlist: bool = False
    selected_indices: Optional[List[int]] = None


# ------------------ Web Routes ------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Renders the main single-page UI."""
    ffmpeg_available = bool(get_ffmpeg_path())
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"ffmpeg_available": ffmpeg_available}
    )


# ------------------ API Endpoints ------------------
@app.get("/api/health")
async def health_check():
    """Returns server and FFmpeg status."""
    ffmpeg_path = get_ffmpeg_path()
    return {
        "status": "healthy",
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "active_tasks_count": len(task_manager.tasks)
    }


@app.post("/api/metadata")
async def get_metadata(req: MetadataRequest):
    """Fetches video or playlist details without starting a download."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please provide a valid YouTube URL.")

    # Run extraction in a separate thread so as not to block asyncio loop
    try:
        data = await asyncio.to_thread(extract_media_metadata, url, req.is_playlist)
        return JSONResponse(content={"success": True, "data": data})
    except ValueError as ve:
        logger.warning(f"Metadata extraction error: {ve}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(ve)})
    except Exception as e:
        logger.error(f"Unexpected error in metadata: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": f"Failed to extract video information: {str(e)}"})


@app.post("/api/download")
async def start_download(req: DownloadRequest):
    """Enqueues a background download task and returns its task_id."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Invalid URL specified.")

    task_id = str(uuid.uuid4())
    task_manager.create_task(task_id=task_id, title="Preparing download...")

    # Spawn download worker in background thread
    asyncio.create_task(
        asyncio.to_thread(
            execute_download,
            task_manager=task_manager,
            task_id=task_id,
            url=url,
            format_type=req.format_type,
            quality=req.quality,
            is_playlist=req.is_playlist,
            selected_indices=req.selected_indices
        )
    )

    return JSONResponse(content={
        "success": True,
        "task_id": task_id,
        "message": "Download task queued successfully."
    })


@app.get("/api/progress/{task_id}")
async def stream_progress(task_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream real-time download progress.
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Download task not found.")

    async def event_generator():
        import json
        last_status = None
        last_percent = None

        # Stream updates until task finishes or errors out
        while True:
            current_task = task_manager.get_task(task_id)
            if not current_task:
                yield f"event: error\ndata: {json.dumps({'error': 'Task expired or removed'})}\n\n"
                break

            status = current_task.get("status")
            percent = current_task.get("percent")

            # Format payload
            payload = {
                "task_id": task_id,
                "status": status,
                "percent": percent,
                "speed_str": current_task.get("speed_str"),
                "eta_str": current_task.get("eta_str"),
                "downloaded_bytes_str": current_task.get("downloaded_bytes_str"),
                "total_bytes_str": current_task.get("total_bytes_str"),
                "filename": current_task.get("filename"),
                "file_size_str": current_task.get("file_size_str"),
                "download_url": current_task.get("download_url"),
                "error_message": current_task.get("error_message"),
            }

            yield f"data: {json.dumps(payload)}\n\n"

            if status in ["completed", "error", "cancelled"]:
                break

            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    """Polling fallback for clients where SSE isn't supported."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(content=task)


@app.get("/api/download/{task_id}")
async def download_file(task_id: str, background_tasks: BackgroundTasks):
    """
    Serves the prepared media file to the user and schedules auto-cleanup after 120 seconds.
    """
    task = task_manager.get_task(task_id)
    if not task or task.get("status") != "completed":
        raise HTTPException(status_code=404, detail="File is not ready or task not found.")

    file_path_str = task.get("file_path")
    if not file_path_str or not os.path.exists(file_path_str):
        raise HTTPException(status_code=404, detail="Downloaded media file was not found on server.")

    file_path = Path(file_path_str)
    filename = task.get("filename") or file_path.name
    encoded_filename = quote(filename)

    # Schedule delayed auto-cleanup (2 minutes after download starts)
    task_dir = DOWNLOADS_DIR / task_id
    background_tasks.add_task(AutoCleanupService.delayed_cleanup, task_id=task_id, target_dir=task_dir, delay_seconds=120)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


@app.post("/api/cancel/{task_id}")
async def cancel_download(task_id: str):
    """Cancels an active download task."""
    success = task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or already finished.")
    return JSONResponse(content={"success": True, "message": "Download task cancelled."})


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "false").lower() in ("true", "1", "t")
    uvicorn.run("app:app", host=host, port=port, reload=reload)

