@echo off
REM Publish the encrypted dashboard to GitHub Pages now (the scanner also does this every 15 minutes).
cd /d "%~dp0"
".venv\Scripts\python.exe" signals.py >nul
".venv\Scripts\python.exe" publish.py
pause
