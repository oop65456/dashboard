@echo off
REM One-time setup: makes a private Python environment (.venv), installs packages, creates .env, runs the check.
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  %PY% -m venv .venv || (echo Python not found. Install Python 3.10+ from python.org and tick "Add to PATH". & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if not exist ".env" copy ".env.example" ".env" >nul && echo Created .env - open it in Notepad to add your free keys later.
echo.
".venv\Scripts\python.exe" check_setup.py
pause
