@echo off
setlocal

set "BASE_DIR=%~dp0"
cd /d "%BASE_DIR%"

:: Set ALL variables FIRST before any goto
set "REBUILD_SCRIPT=%BASE_DIR%rebuild_upcoming_dividends.py"
set "XLSX_PATH=%BASE_DIR%upcoming_dividends_latest.xlsx"
set "VENV_PYTHON=%BASE_DIR%..\..\.venv\Scripts\python.exe"

if not exist "%REBUILD_SCRIPT%" (
  echo ERROR: Script not found: "%REBUILD_SCRIPT%"
  pause >nul
  exit /b 1
)

:: Find Python
if exist "%VENV_PYTHON%" (
  set "PYTHON_EXE=%VENV_PYTHON%"
  goto :run
)

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=py"
  goto :run
)

set "PYTHON_EXE=python"

:run
echo Running: "%PYTHON_EXE%" "%REBUILD_SCRIPT%" --days-ahead 45 --throttle 0.15
"%PYTHON_EXE%" "%REBUILD_SCRIPT%" --days-ahead 45 --throttle 0.15
if errorlevel 1 (
  echo Rebuild failed. Press any key to exit.
  pause >nul
  exit /b 1
)

start "" "%XLSX_PATH%"
exit /b 0
