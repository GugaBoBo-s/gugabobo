@echo off
setlocal

set "PROJECT_DIR=%~dp0.."
cd /d "%PROJECT_DIR%"

if not exist ".venv\Scripts\gugabobo.exe" (
  echo [gugabobo] Missing .venv. Run setup first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
  pause
  exit /b 1
)

echo [gugabobo] Starting API and dashboard...
echo [gugabobo] Dashboard: http://127.0.0.1:8765/dashboard
echo [gugabobo] Press Ctrl+C to stop.
".venv\Scripts\gugabobo.exe" api

endlocal
