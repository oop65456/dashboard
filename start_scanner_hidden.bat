@echo off
REM Start the scanner in the background (no window). Dashboard: http://127.0.0.1:8000  Stop: stop_scanner.bat
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" run_scanner.py --no-open
echo Scanner started in the background. Dashboard: http://127.0.0.1:8000
timeout /t 3 >nul
