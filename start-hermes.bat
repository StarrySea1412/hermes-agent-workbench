@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   Hermes Gateway Startup
echo ========================================
echo.

where hermes >nul 2>nul
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Python" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
      if not defined HERMES_EXE if exist "%%~fD\Scripts\hermes.exe" set "HERMES_EXE=%%~fD\Scripts\hermes.exe"
    )
  )
  if exist "%APPDATA%\Python" (
    for /d %%D in ("%APPDATA%\Python\Python*") do (
      if not defined HERMES_EXE if exist "%%~fD\Scripts\hermes.exe" set "HERMES_EXE=%%~fD\Scripts\hermes.exe"
    )
  )
  if not defined HERMES_EXE (
    echo Hermes CLI was not found in PATH.
    echo Expected command: hermes gateway run --accept-hooks
    echo.
    echo Install or expose Hermes first, then rerun this script.
    pause
    exit /b 1
  )
) else (
  set "HERMES_EXE=hermes"
)

echo Starting Hermes Gateway on the local API server port...
echo Expected local API: http://127.0.0.1:8642/v1
echo Press Ctrl+C to stop the gateway.
echo.

if "%HERMES_HOME%"=="" set "HERMES_HOME=%~dp0.hermes-runtime"
set "API_SERVER_ENABLED=true"
set "API_SERVER_HOST=127.0.0.1"
set "API_SERVER_PORT=8642"
set "API_SERVER_KEY=dev-test-key-for-local"
if "%API_SERVER_MODEL_NAME%"=="" call :LoadHermesModelName "%HERMES_HOME%\config.yaml"
set "API_SERVER_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
set "HERMES_ACCEPT_HOOKS=1"

echo API Server env:
echo   HERMES_HOME=%HERMES_HOME%
echo   API_SERVER_ENABLED=%API_SERVER_ENABLED%
echo   API_SERVER_HOST=%API_SERVER_HOST%
echo   API_SERVER_PORT=%API_SERVER_PORT%
if "%API_SERVER_MODEL_NAME%"=="" (
  echo   API_SERVER_MODEL_NAME=not set - Hermes will use config/default behavior
) else (
  echo   API_SERVER_MODEL_NAME=%API_SERVER_MODEL_NAME%
)
echo.

"%HERMES_EXE%" gateway run --accept-hooks
exit /b %ERRORLEVEL%

:LoadHermesModelName
set "CONFIG_PATH=%~1"
if not exist "%CONFIG_PATH%" exit /b 0

for /f "usebackq tokens=1,* delims=:" %%A in ("%CONFIG_PATH%") do (
  set "CONFIG_KEY=%%A"
  set "CONFIG_VALUE=%%B"
  set "CONFIG_KEY=!CONFIG_KEY: =!"
  for /f "tokens=* delims= " %%V in ("!CONFIG_VALUE!") do set "CONFIG_VALUE=%%V"
  if /I "!CONFIG_KEY!"=="default" (
    if defined CONFIG_VALUE (
      set "API_SERVER_MODEL_NAME=!CONFIG_VALUE!"
      exit /b 0
    )
  )
  if /I "!CONFIG_KEY!"=="name" (
    if defined CONFIG_VALUE (
      set "API_SERVER_MODEL_NAME=!CONFIG_VALUE!"
      exit /b 0
    )
  )
)
exit /b 0
