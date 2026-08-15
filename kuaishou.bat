@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Kuaishou Downloader (video / atlas)
echo ==========================================
if not exist kuaishou_cookies.txt (
  echo WARN: kuaishou_cookies.txt not found. Anonymous mode may hit risk control.
  echo Export it first: open kuaishou.com in Edge, click the
  echo cookie-export extension, then move the file here.
  echo.
)
echo Paste a Kuaishou link (v.kuaishou.com / short-video / f/), press Enter:
set /p url=
if "%url%"=="" exit /b
echo Downloading...
.venv\Scripts\python.exe kuaishou.py "%url%"
echo.
pause
