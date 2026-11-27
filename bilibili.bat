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
rem 4K / 1080P60 需要大会员登录态：有 bilibili_cookies.txt 就带上，没有则只到 1080P
rem yt-dlp 退出会把 cookiejar 写回 cookiefile，所以传临时副本，别改用户的导出文件
set "CK="
set "CKFILE=%~dp0_bili_ck_run.txt"
del "%CKFILE%" 2>nul
if exist "%~dp0bilibili_cookies.txt" copy /y "%~dp0bilibili_cookies.txt" "%CKFILE%" >nul
if exist "%CKFILE%" set CK=--cookies "%CKFILE%"
echo Downloading...
.venv\Scripts\python.exe -m yt_dlp --no-playlist --proxy "" %CK% --ffmpeg-location "%~dp0ffmpeg" -f "bv*[vcodec^=avc1]+ba[ext=m4a]/bv*+ba/b" -o "downloads\%%(title)s [%%(id)s].%%(ext)s" "%url%"
del "%CKFILE%" 2>nul
echo.
pause
