@echo off
REM Update prices and news, then compute signals into public\signals.json and show a summary.
cd /d "%~dp0"
".venv\Scripts\python.exe" collect.py
".venv\Scripts\python.exe" news.py
".venv\Scripts\python.exe" signals.py
pause
