@echo off
setlocal enabledelayedexpansion
title TrustDocs Startup Manager

echo ========================================================
echo   TrustDocs Environment Startup
echo ========================================================
echo [1] Headless Mode (Background, suppress new windows ^& logs to NUL)
echo [2] Normal Mode   (Open terminal windows for all services)
echo.
choice /C 12 /N /M "Select Startup Mode [1-2]: "
if errorlevel 2 (
    set HEADLESS=0
    echo.
    echo Starting in Normal Mode...
) else (
    set HEADLESS=1
    echo.
    echo Starting in Headless Mode...
)
echo.
echo ========================================================
echo   Starting TrustDocs Environment...
echo ========================================================
echo.

echo [1/3] Starting PostgreSQL Cluster (Primary ^& Replica)...
docker-compose up -d

echo Waiting for database to be ready (this may take a moment)...
:wait_db
for /f "tokens=*" %%i in ('docker inspect --format="{{if .Config.Healthcheck}}{{print .State.Health.Status}}{{end}}" trustdocs-pg-primary') do set status=%%i
if not "%status%"=="healthy" (
    timeout /t 2 /nobreak >nul
    goto wait_db
)
:wait_db_replica
for /f "tokens=*" %%i in ('docker inspect --format="{{if .Config.Healthcheck}}{{print .State.Health.Status}}{{end}}" trustdocs-pg-replica') do set status_replica=%%i
if not "%status_replica%"=="healthy" (
    timeout /t 2 /nobreak >nul
    goto wait_db_replica
)
echo Database cluster is ready!
echo.

echo [2/3] Starting Backend (Uvicorn)...
:: Stop any process running on port 8100
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8100') do (
    if not "%%a"=="0" taskkill /F /T /PID %%a 2>nul
)

:: Start backend
if "%HEADLESS%"=="1" (
    start /B "" cmd /c "cd /d "%~dp0" && venv\Scripts\python.exe -m uvicorn trustdocs.app:app --host 127.0.0.1 --port 8100 --reload > NUL 2>&1"
) else (
    start "TrustDocs_Backend" cmd /c "title TrustDocs_Backend && cd /d "%~dp0" && venv\Scripts\python.exe -m uvicorn trustdocs.app:app --host 127.0.0.1 --port 8100 --reload"
)

echo Waiting for backend to spin up...
timeout /t 3 /nobreak >nul
echo Backend started.
echo.

echo [3/3] Starting Frontend (Vite)...
:: Stop any process running on port 5173
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173') do (
    if not "%%a"=="0" taskkill /F /T /PID %%a 2>nul
)

:: Start frontend
if "%HEADLESS%"=="1" (
    start /B "" cmd /c "cd /d "%~dp0trustdocs-ui" && npm run dev > NUL 2>&1"
) else (
    start "TrustDocs_Frontend" cmd /c "title TrustDocs_Frontend && cd /d "%~dp0trustdocs-ui" && npm run dev"
)

:: Open browser for developer ease
if "%HEADLESS%"=="0" (
    timeout /t 5 /nobreak >nul
    start "" "http://localhost:5173"
)

echo.
echo ========================================================
echo   Environment successfully started! 
echo.
echo   - Backend:  http://127.0.0.1:8100
echo   - Frontend: http://localhost:5173
echo.
echo   [KILLSWITCH]
echo   Press ANY KEY in this window to stop all services,
echo   close the spawned terminals, and shutdown databases.
echo ========================================================
pause >nul

echo.
echo Shutting down services...

:: Kill by Window Title (closes the spawned terminal windows and their children)
taskkill /FI "WINDOWTITLE eq TrustDocs_Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq TrustDocs_Frontend*" /T /F >nul 2>&1

:: Double check ports to kill any zombies
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8100') do (
    if not "%%a"=="0" taskkill /F /T /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173') do (
    if not "%%a"=="0" taskkill /F /T /PID %%a >nul 2>&1
)

echo Stopping PostgreSQL containers...
docker-compose stop >nul 2>&1

echo.
echo ========================================================
echo   All spawned terminals and services have been stopped.
echo   You can safely close this window.
echo ========================================================
timeout /t 5 >nul
