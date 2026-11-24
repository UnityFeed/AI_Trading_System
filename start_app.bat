@echo off
REM Double-click this file to start the BTC trading app.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Could not find .venv\Scripts\python.exe in this folder.
  echo Create the virtual environment first, see CLAUDE.md.
  pause
  exit /b 1
)
REM Install the libraries the first time (or after an update added one).
".venv\Scripts\python.exe" -c "import numpy, sklearn, lightgbm, tzdata" 2>nul || (
  echo Installing the required libraries once, see requirements.txt ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" -m scripts.run_app
pause
