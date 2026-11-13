@echo off
REM Ask the scanner to stop (it checks every few seconds and finishes its current step first).
cd /d "%~dp0"
type nul > "data\STOP"
echo Stop requested. The scanner will finish its current step and exit within about a minute.
timeout /t 5 >nul
