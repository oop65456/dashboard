@echo off
REM Open the dashboard. Starts the scanner in this window if it is not running yet.
title Signal Dashboard scanner
cd /d "%~dp0"
".venv\Scripts\python.exe" run_scanner.py
