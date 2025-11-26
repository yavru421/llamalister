@echo off
echo LlamaLister Portable Launcher
echo ==============================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://python.org
    echo and make sure it's added to your system PATH.
    echo.
    pause
    exit /b 1
)

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Set Python path to include the current directory
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"

echo Starting LlamaLister...
echo.

REM Run the application
python "%SCRIPT_DIR%llamalister\llamalister.py"

echo.
echo LlamaLister has exited.
pause