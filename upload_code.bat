@echo off
REM Upload the code (never keys or data) to GitHub. Shows the file list and asks first.
cd /d "%~dp0"
".venv\Scripts\python.exe" upload_code.py
pause
