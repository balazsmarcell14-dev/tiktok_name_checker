@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe tiktok_checker.py
) else (
    echo [ERROR] Not installed yet! Run INSTALL.bat first.
)
pause
