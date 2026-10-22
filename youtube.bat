@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   YouTube Downloader (video / playlist)
echo ==========================================
echo Paste a YouTube link (watch / youtu.be / shorts / live / playlist), press Enter:
echo   [*] YouTube is blocked in mainland China: turn on Clash "system proxy" first
set /p url=
if "%url%"=="" exit /b
echo.
echo Download the WHOLE playlist if the link carries one? (y/N)
set /p pl=
set "opt="
if /i "%pl%"=="y" set "opt=--playlist"
echo Downloading...
.venv\Scripts\python.exe youtube.py "%url%" %opt%
echo.
pause
