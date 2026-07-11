@echo off
chcp 65001 >nul
title AI Agent Platform - Local Dev

echo ========================================
echo   AI Agent Platform - 本地开发环境
echo ========================================
echo.

REM ---- 1. Docker services ----
echo [1/3] 启动数据库服务...
docker compose -f "E:\项目\ai-agent-platform\docker-compose.yml" up -d postgres redis 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Docker 未运行，请先启动 Docker Desktop
    pause
    exit /b 1
)

REM Wait for PostgreSQL
echo       等待 PostgreSQL 就绪...
:wait_db
timeout /t 2 /nobreak >nul
docker compose -f "E:\项目\ai-agent-platform\docker-compose.yml" exec -T postgres pg_isready -U agent -d aiagent >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto wait_db
echo [1/3] PostgreSQL + Redis 已就绪

REM ---- 2. Backend ----
echo [2/3] 启动后端 http://localhost:8000 ...
start "AI Backend" cmd /c "cd /d E:\项目\ai-agent-platform\backend && C:\Users\甘俊培\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

REM ---- 3. Frontend ----
echo [3/3] 启动前端 http://localhost:5173 ...
start "AI Frontend" cmd /c "cd /d E:\项目\ai-agent-platform\frontend && C:\Users\甘俊培\.workbuddy\binaries\node\versions\22.22.2\node.exe node_modules\vite\bin\vite.js --host"

echo.
echo ========================================
echo   全部启动!
echo.
echo   前端:  http://localhost:5173
echo   后端:  http://localhost:8000
echo   API:   http://localhost:8000/docs
echo ========================================
echo.
echo 按任意键停止服务...
pause >nul

taskkill /FI "WINDOWTITLE eq AI Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI Frontend*" /T /F >nul 2>&1
echo 已停止
