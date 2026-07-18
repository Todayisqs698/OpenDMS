@echo off
chcp 65001 >nul
echo ========================================
echo   EdgeGuard - One-Click Setup
echo ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found

if not exist "..\edgeguard-venv\" (
    echo [1/3] Creating virtual environment...
    python -m venv ..\edgeguard-venv
) else (
    echo [1/3] Virtual environment exists, skip
)

echo [2/3] Installing dependencies...
..\edgeguard-venv\Scripts\python.exe -m pip install --upgrade pip --quiet
..\edgeguard-venv\Scripts\python.exe -m pip install opencv-python mediapipe openai-whisper numpy langchain langchain-deepseek langgraph fastapi uvicorn websockets pydantic python-dotenv --quiet

echo [3/3] Checking face model...
if not exist "modules\vision\face_landmarker_v2_with_blendshapes.task" (
    echo   Downloading MediaPipe face model...
    ..\edgeguard-venv\Scripts\python.exe -c "import urllib.request; urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task', 'modules/vision/face_landmarker_v2_with_blendshapes.task')"
    echo   Done
) else (
    echo   Face model exists, skip
)

echo.
echo ========================================
echo   Setup complete! Run start.bat to launch
echo ========================================
pause
