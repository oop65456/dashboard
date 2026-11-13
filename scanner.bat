@echo off
REM Run the scanner in this window (you see every update). Close the window or run stop_scanner.bat to stop.
title Signal Dashboard scanner
cd /d "%~dp0"
".venv\Scripts\python.exe" run_scanner.py
pause
