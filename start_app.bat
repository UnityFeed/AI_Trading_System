@echo off
REM Double-click this file to start the BTC trading app.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Could not find .venv\Scripts\python.exe in this folder.
  echo Create the virtual environment first, see CLAUDE.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.run_app
pause
