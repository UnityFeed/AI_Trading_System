@echo off
REM Double-click to record Kraken order book and buy/sell flow (keep the window open).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Could not find .venv\Scripts\python.exe in this folder.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.record_order_flow
pause
