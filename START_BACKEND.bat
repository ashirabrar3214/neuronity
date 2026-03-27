@echo off
REM Start the backend server using the virtual environment

echo Starting Easy Company Backend...
echo.

cd /d "%~dp0"

REM Check if .venv exists
if not exist ".venv" (
    echo ERROR: Virtual environment not found!
    echo Please create it first.
    pause
    exit /b 1
)

REM Check if Python exists in venv
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python not found in virtual environment!
    pause
    exit /b 1
)

echo Virtual environment found.
echo Installing dependencies...

REM Install required packages
.venv\Scripts\pip.exe install trafilatura beautifulsoup4 spacy -q 2>nul

echo.
echo Starting server on http://localhost:8000...
echo Press Ctrl+C to stop the server
echo.

REM Start the backend
.venv\Scripts\python.exe backend\interpreter.py

pause
