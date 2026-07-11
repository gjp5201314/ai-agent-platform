@echo off
chcp 65001 >nul
title AI Agent Platform - Local Dev Server

echo ========================================
echo   AI Agent Platform - 本地开发环境
echo ========================================
echo.

REM ---- 1. Start Docker services (DB + Redis) ----
echo [1/4] 启动数据库服务 (PostgreSQL + Redis)...
docker compose -f "E:\项目\ai-agent-platform\docker-compose.yml" up -d postgres redis
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Docker 启动失败，请确保 Docker Desktop 正在运行
    echo 手动步骤:
    echo   1. 打开 Docker Desktop
    echo   2. 确认左下角显示 "Engine running"
    echo   3. 重新运行此脚本
    pause
    exit /b 1
)
echo [1/4] 数据库服务已启动

REM ---- 2. Wait for DB to be ready ----
echo [2/4] 等待数据库就绪...
:wait_db
timeout /t 3 /nobreak >nul
docker compose -f "E:\项目\ai-agent-platform\docker-compose.yml" exec -T postgres pg_isready -U agent -d aiagent >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   等待中...
    goto wait_db
)
echo [2/4] 数据库已就绪

REM ---- 3. Start Backend ----
echo [3/4] 启动后端 (FastAPI + LangGraph)...
start "AI Agent Backend" cmd /c "cd /d E:\项目\ai-agent-platform\backend && C:\Users\甘俊培\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
echo [3/4] 后端已启动 (http://localhost:8000)

REM ---- 4. Start Frontend ----
echo [4/4] 启动前端 (Vite + React)...
start "AI Agent Frontend" cmd /c "cd /d E:\项目\ai-agent-platform\frontend && C:\Users\甘俊培\.workbuddy\binaries\node\versions\22.22.2\node.exe node_modules\vite\bin\vite.js --host"
echo [4/4] 前端已启动 (http://localhost:5173)

echo.
echo ========================================
echo   全部服务已启动!
echo.
echo   前端:  http://localhost:5173
echo   后端:  http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo.
echo   按任意键停止所有服务...
echo ========================================
pause >nul

REM ---- Cleanup ----
echo.
echo 正在停止服务...
taskkill /FI "WINDOWTITLE eq AI Agent Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI Agent Frontend*" /T /F >nul 2>&1
docker compose -f "E:\项目\ai-agent-platform\docker-compose.yml" down
echo 已停止所有服务
