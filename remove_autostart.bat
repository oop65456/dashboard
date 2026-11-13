@echo off
REM Stop starting the scanner at login.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\SignalDashboard Scanner.bat" (del "%STARTUP%\SignalDashboard Scanner.bat" & echo Removed: the scanner no longer starts at login.) else (echo It was not set to start at login.)
pause
