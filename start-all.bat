@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Hermes Agent Workbench Startup
echo ========================================
echo.

echo Starting backend and frontend services...
echo.

start "Hermes Gateway" cmd /k "cd /d %~dp0 && start-hermes.bat"

timeout /t 3 /nobreak >nul

start "Hermes Workbench Backend" cmd /k "cd /d %~dp0backend && start.bat"

timeout /t 3 /nobreak >nul

start "Hermes Workbench Frontend" cmd /k "cd /d %~dp0ai-skill-app && start.bat"

echo.
echo ========================================
echo   Services are starting...
echo.
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://127.0.0.1:5173
echo   Hermes:   http://127.0.0.1:8642/v1
echo   API Docs: http://127.0.0.1:8000/api/docs/
echo.
echo   Login: admin / admin123
echo ========================================
echo.
echo You can close this launcher window after the service windows open.
pause >nul
