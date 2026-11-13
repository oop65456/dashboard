@echo off
REM Update the price archive in data\ (only new bars are downloaded).
cd /d "%~dp0"
".venv\Scripts\python.exe" collect.py %*
pause
