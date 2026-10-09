import os
import shutil
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from downloader import DownloadTaskManager

logger = logging.getLogger(__name__)

# Default file retention period: 20 minutes
MAX_FILE_AGE_SECONDS = 20 * 60

class AutoCleanupService:
    """
    Automated background cleanup service to prevent disk overflow:
    1. Scans and deletes temporary task directories older than MAX_FILE_AGE_SECONDS.
    2. Provides delayed cleanup trigger after user initiates a download.
    """
    def __init__(self, downloads_dir: Path, task_manager: Optional["DownloadTaskManager"] = None, interval_seconds: int = 300):
        self.downloads_dir = downloads_dir
        self.task_manager = task_manager
        self.interval_seconds = interval_seconds
        self.is_running = False

    async def start(self):
        """Runs the background periodic cleanup loop."""
        self.is_running = True
        logger.info(f"Auto-cleanup background worker started (Interval: {self.interval_seconds}s, Retention: {MAX_FILE_AGE_SECONDS // 60}m)")
        while self.is_running:
            try:
                self.purge_expired_files()
            except Exception as e:
                logger.error(f"Error during periodic file cleanup: {e}")
            await asyncio.sleep(self.interval_seconds)

    def stop(self):
        self.is_running = False

    def purge_expired_files(self):
        """Scans the downloads directory and removes any expired task folder or file."""
        if not self.downloads_dir.exists():
            return

        now = time.time()
        removed_count = 0

        for item in self.downloads_dir.iterdir():
            try:
                mtime = item.stat().st_mtime
                age_seconds = now - mtime

                if age_seconds > MAX_FILE_AGE_SECONDS:
                    task_id = item.name
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                    removed_count += 1
                    logger.info(f"Auto-cleaned expired directory/file: {item.name} (Age: {int(age_seconds // 60)} mins)")

                    # Also remove from task manager memory
                    if self.task_manager and task_id:
                        self.task_manager.remove_task(task_id)
            except Exception as e:
                logger.warning(f"Could not purge {item}: {e}")

        if removed_count > 0:
            logger.info(f"Periodic cleanup completed. Removed {removed_count} expired items.")

    @staticmethod
    async def delayed_cleanup(task_id: str, target_dir: Path, delay_seconds: int = 120):
        """
        Delayed file cleanup triggered after user initiates download.
        Waits `delay_seconds` (e.g. 2 mins for large files to finish streaming) before safely deleting the file.
        """
        logger.info(f"Scheduled delayed cleanup for task {task_id} in {delay_seconds} seconds.")
        await asyncio.sleep(delay_seconds)
        try:
            if target_dir.exists():
                if target_dir.is_dir():
                    shutil.rmtree(target_dir, ignore_errors=True)
                else:
                    target_dir.unlink(missing_ok=True)
                logger.info(f"Successfully cleaned up temporary files for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed delayed cleanup for task {task_id}: {e}")
