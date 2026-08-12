@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Douyin Downloader (album / video)
echo ==========================================
if not exist douyin_cookies.txt (
  echo ERROR: douyin_cookies.txt not found.
  echo Export it first: open douyin.com in Edge, click the
  echo cookie-export extension, then move the file here.
  echo.
  pause
  exit /b
)
echo Paste a Douyin share link, then press Enter:
set /p url=
if "%url%"=="" exit /b
echo Downloading...
.venv\Scripts\python.exe douyin.py "%url%"
echo.
pause
