@echo off
REM Opens your .env key file in Notepad (creates it from the template first if needed).
cd /d "%~dp0"
if not exist ".env" copy ".env.example" ".env" >nul
notepad ".env"
