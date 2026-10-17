@echo off
REM Creates a virtual environment and installs everything PC Tweaker needs.
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (
  echo Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this file again.
  pause & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv || (echo Failed to create the virtual environment. & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Dependency install failed. & pause & exit /b 1)
echo.
echo Setup complete. Start the app with run.bat  (or run_as_admin.bat for all features).
pause
