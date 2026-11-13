@echo off
REM Start the scanner in the background every time you log in to Windows (no admin rights needed).
REM It adds one small file to your Startup folder. Undo with remove_autostart.bat.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
(
  echo @echo off
  echo cd /d "%~dp0"
  echo start "" ".venv\Scripts\pythonw.exe" run_scanner.py --no-open
) > "%STARTUP%\SignalDashboard Scanner.bat"
echo Done: the scanner will start automatically when you log in.
echo File added: %STARTUP%\SignalDashboard Scanner.bat
pause
