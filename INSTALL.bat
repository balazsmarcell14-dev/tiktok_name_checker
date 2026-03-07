@echo off
echo ==================================================
echo        TikTok Checker - Installation
echo ==================================================
echo.

:: Find Python
set PYTHON=
python --version >nul 2>&1 && set PYTHON=python
if not defined PYTHON (
    py --version >nul 2>&1 && set PYTHON=py
)
if not defined PYTHON (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" set PYTHON=%%D\python.exe
    )
)
if not defined PYTHON (
    for /d %%D in ("C:\Python*") do (
        if exist "%%D\python.exe" set PYTHON=%%D\python.exe
    )
)
if not defined PYTHON (
    echo [ERROR] Python is not installed!
    echo Please download and install Python from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)
echo Found Python: %PYTHON%

echo [1/3] Creating virtual environment...
%PYTHON% -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate
pip install playwright
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/3] Installing Chromium browser...
playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Chromium.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo        Installation complete!
echo        Run RUN.bat to start the checker.
echo ==================================================
pause
