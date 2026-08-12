@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Bilibili Downloader (yt-dlp)
echo ==========================================
echo Paste a Bilibili link (BV/av/b23.tv), press Enter:
set /p url=
if "%url%"=="" exit /b
rem Auto-fill URL if user pasted a bare BV/av number or b23.tv short link
set "u2=%url:~0,2%"
if /i "%u2%"=="BV" set "url=https://www.bilibili.com/video/%url%"
if /i "%u2%"=="av" set "url=https://www.bilibili.com/video/%url%"
if /i "%u2%"=="b2" set "url=https://%url%"
echo Downloading...
.venv\Scripts\python.exe -m yt_dlp --no-playlist --ffmpeg-location "%~dp0ffmpeg" -f "bv*+ba/b" -o "downloads\%%(title)s [%%(id)s].%%(ext)s" "%url%"
echo.
pause
