@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Hermes Workbench Backend Startup
echo ========================================
echo.

if not exist "venv\Scripts\python.exe" (
  echo Missing backend virtual environment: backend\venv
  echo Create the venv and install requirements first.
  pause
  exit /b 1
)

if "%HERMES_GATEWAY_URL%"=="" set "HERMES_GATEWAY_URL=http://127.0.0.1:8642/v1"
if "%HERMES_GATEWAY_KEY%"=="" set "HERMES_GATEWAY_KEY=dev-test-key-for-local"

echo Hermes Gateway:
echo   URL=%HERMES_GATEWAY_URL%
echo   KEY=configured
echo.

echo Applying database migrations...
venv\Scripts\python.exe manage.py migrate
if errorlevel 1 (
  echo Migration failed.
  pause
  exit /b 1
)

echo Ensuring local demo login...
venv\Scripts\python.exe manage.py ensure_demo_user --username admin --password admin123 --force-password
if errorlevel 1 (
  echo Demo user setup failed.
  pause
  exit /b 1
)

echo Syncing default AI configuration...
venv\Scripts\python.exe manage.py sync_ai_config --username admin --overwrite-key
if errorlevel 1 (
  echo AI configuration sync failed.
  pause
  exit /b 1
)

echo Syncing Hermes runtime configuration...
venv\Scripts\python.exe manage.py sync_hermes_config --username admin
if errorlevel 1 (
  echo Hermes runtime configuration sync failed.
  pause
  exit /b 1
)

echo.
echo Starting Django API: http://127.0.0.1:8000
echo Press Ctrl+C to stop the server.
echo.
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
