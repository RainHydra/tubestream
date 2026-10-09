@echo off
echo ========================================================
echo   Starting TubeStream Pro - YouTube Media Downloader
echo ========================================================
echo.
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
