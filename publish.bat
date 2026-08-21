@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ==========================================
echo   一键发布：升版本 + commit + tag + push
echo   用法: publish.bat [patch|minor|major]
echo   默认 patch（1.2.0 -^> 1.2.1）
echo ==========================================
.venv\Scripts\python.exe publish.py %*
if errorlevel 1 (
    echo.
    echo 发布中止，请查看上方提示。
    pause
    exit /b 1
)
echo.
echo 发布完成！GitHub Actions 正在自动构建 Release。
pause
