@echo off
REM Run the connection check again (e.g. after adding a key to .env).
cd /d "%~dp0"
".venv\Scripts\python.exe" check_setup.py
pause
