@echo off
chcp 65001 >nul 2>nul
echo ========================================
echo   EdgeGuard - One-Click Start
echo ========================================
echo.

set ROOT=%~dp0
REM PATH python resolves to anaconda base (3.8, no fastapi/uvicorn) - must use Python 3.13
set PYTHON=py -3.13

REM -- dependency check --
echo [i] Checking dependencies...
%PYTHON% -c "import fastapi, uvicorn, cv2, httpx, edge_tts, mediapipe" >nul 2>nul
if errorlevel 1 (
    echo [!] Missing core deps. Run: py -3.13 -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo [i] Using Python 3.13 via py launcher

REM -- optional: AMAP API Key (search_attractions tool) --
if "%AMAP_API_KEY%"=="" (
    echo [i] AMAP_API_KEY not set - search_attractions tool will return fallback results
) else (
    echo [i] AMAP_API_KEY detected - search_attractions tool enabled
)

echo.
echo Select mode:
echo   [1] Full mode  (backend + frontend)
echo   [2] Web only   (backend + frontend, no camera AI)
set /p MODE=Enter 1/2 [default 1]:
if "%MODE%"=="" set MODE=1

echo.
echo [1/2] Starting backend (FastAPI :8000)...
start "EdgeGuard Backend" cmd /k "cd /d %ROOT%backend && %PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

echo [2/2] Starting frontend (Vite :8005)...
start "EdgeGuard Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo ========================================
echo   Backend:   http://localhost:8000
echo   Frontend:  http://localhost:8005
echo   API docs:  http://localhost:8000/docs
echo ========================================
echo.
echo Close the windows to stop all services.
pause
