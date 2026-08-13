@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Build douyin-dl.exe (PyInstaller)
echo ==========================================

if not exist .venv\Scripts\python.exe (
  echo [FAIL] venv not found. Run: python -m venv .venv
  pause
  exit /b 1
)

echo [*] Ensuring deps (requests, yt-dlp, pyinstaller)...
.venv\Scripts\python.exe -m pip install -q requests yt-dlp pyinstaller
if errorlevel 1 (
  echo [FAIL] pip install failed.
  pause
  exit /b 1
)

.venv\Scripts\python.exe build.py
if errorlevel 1 (
  echo [FAIL] build failed.
  pause
  exit /b 1
)

echo.
echo [OK] Send dist\抖音下载器.exe + extensions\cookie-export + README to your users.
pause
