@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   Build douyin-dl.exe (PyInstaller)
echo ==========================================

if not exist .venv\Scripts\pyinstaller.exe (
  echo [*] Installing PyInstaller into venv...
  .venv\Scripts\python.exe -m pip install pyinstaller
  if errorlevel 1 (
    echo [FAIL] pip install pyinstaller failed.
    pause
    exit /b 1
  )
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
