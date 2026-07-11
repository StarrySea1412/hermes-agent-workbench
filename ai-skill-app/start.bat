@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Hermes Workbench Frontend Startup
echo ========================================
echo.

if not exist "node_modules" (
  echo Installing dependencies...
  npm install
  if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
)

echo.
echo ========================================
echo   Starting development server
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo Press Ctrl+C to stop the server.
echo.

npm run dev
