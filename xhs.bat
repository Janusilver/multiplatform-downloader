@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Xiaohongshu Downloader (images / video)
echo ==========================================
if not exist xhs_cookies.txt (
  echo WARN: xhs_cookies.txt not found. Anonymous mode may hit risk control.
  echo Export it first: open xiaohongshu.com in Edge, click the
  echo cookie-export extension, then move the file here.
  echo.
)
echo Paste a XHS link (xhslink / explore / discovery / user profile), press Enter:
set /p url=
if "%url%"=="" exit /b
echo Downloading...
.venv\Scripts\python.exe xhs.py "%url%"
echo.
pause
