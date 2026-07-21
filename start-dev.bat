@echo off
chcp 65001 >nul
title AI Agent Platform - Local Dev

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PATH=C:\Program Files\Docker\Docker\resources\bin;%PATH%"
set "PYTHON=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
set "PIP=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\pip.exe"
set "NODE=%USERPROFILE%\.workbuddy\binaries\node\versions\22.22.2\node.exe"

echo ========================================
echo   AI Agent Platform - Local Dev
echo ========================================
echo.
echo   ROOT:   %ROOT%
echo   PYTHON: %PYTHON%
echo   NODE:   %NODE%
echo.

echo [1/4] Starting database services...
docker compose -f "%ROOT%\docker-compose.yml" up -d postgres redis
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker not running. Please start Docker Desktop first.
    pause
    exit /b 1
)
echo       Waiting for PostgreSQL...
:wait_db
timeout /t 2 /nobreak >nul
docker compose -f "%ROOT%\docker-compose.yml" exec -T postgres pg_isready -U agent -d aiagent >nul 2>&1
if %ERRORLEVEL% neq 0 goto wait_db
echo [1/4] PostgreSQL + Redis ready.
echo.

echo [2/4] Checking Python dependencies...
pushd "%ROOT%\backend"
call "%PYTHON%" -c "import loguru" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo       Installing dependencies ^(first run, ~2-3 min^)...
    call "%PIP%" install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        popd
        echo [ERROR] pip install failed. Check your network.
        pause
        exit /b 1
    )
)
popd
echo [2/4] Backend deps OK.
echo.

echo [3/4] Starting backend  http://localhost:8000 ...
start "AI Agent Backend" /D "%ROOT%\backend" cmd /k ""%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [4/4] Starting frontend http://localhost:5173 ...
start "AI Agent Frontend" /D "%ROOT%\frontend" cmd /k ""%NODE%" node_modules\vite\bin\vite.js --host"

echo.
echo ========================================
echo   All services started!
echo.
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo ========================================
echo.
echo Press any key to STOP all services...
pause

taskkill /FI "WINDOWTITLE eq AI Agent Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI Agent Frontend*" /T /F >nul 2>&1
echo All services stopped.
pause
