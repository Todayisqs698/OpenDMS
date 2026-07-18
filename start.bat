@echo off
chcp 65001 >nul
echo ========================================
echo   EdgeGuard - One-Click Start
echo ========================================
echo.

set VENV=%CD%\..\edgeguard-venv\Scripts
set ROOT=%~dp0

REM 检查虚拟环境
if not exist "%VENV%\python.exe" (
    echo [!] VENV not found at %VENV%
    echo     Run setup.bat first, or edit VENV path in this file.
    echo     Falling back to system python...
    set VENV=
)

echo Select mode:
echo   [1] Full mode  (backend + frontend + camera AI)
echo   [2] Dry-run    (backend + frontend + AI no camera)
echo   [3] Web only   (backend + frontend, no AI)
set /p MODE=Enter 1/2/3 [default 1]:
if "%MODE%"=="" set MODE=1

echo.
echo [1/3] Starting backend (FastAPI :8000)...
start "EdgeGuard Backend" cmd /k "cd /d %ROOT%backend && %VENV%python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

echo [2/3] Starting frontend (Vite :8005)...
start "EdgeGuard Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

if "%MODE%"=="3" goto :done

timeout /t 2 /nobreak >nul

if "%MODE%"=="2" (
    echo [3/3] Starting AI engine (dry-run, no camera)...
    start "EdgeGuard AI" cmd /k "cd /d %ROOT% && %VENV%python.exe app.py --dry-run"
) else (
    echo [3/3] Starting AI engine (camera mode)...
    start "EdgeGuard AI" cmd /k "cd /d %ROOT% && %VENV%python.exe app.py"
)

:done
echo.
echo ========================================
if "%MODE%"=="2" (
    echo   Backend:   http://localhost:8000
    echo   Frontend:  http://localhost:8005
    echo   AI:        dry-run (no camera)
) else if "%MODE%"=="3" (
    echo   Backend:   http://localhost:8000
    echo   Frontend:  http://localhost:8005
    echo   AI:        not started
) else (
    echo   Backend:   http://localhost:8000
    echo   Frontend:  http://localhost:8005
    echo   AI:        camera + perception (full)
)
echo   API docs:  http://localhost:8000/docs
echo ========================================
echo.
echo Close the 3 windows to stop all services.
pause
