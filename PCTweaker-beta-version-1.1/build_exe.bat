@echo off
REM Builds dist\PCTweaker.exe (single file, no Python needed to run it).
REM   build_exe.bat          -> normal exe; use the in-app "Restart as admin" button when needed
REM   build_exe.bat admin    -> exe that always asks for administrator rights (UAC) on launch
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || (echo Failed to create the virtual environment. & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt || (echo Dependency install failed. & pause & exit /b 1)
set "UAC="
if /i "%~1"=="admin" set "UAC=--uac-admin"
pyinstaller --noconfirm --clean --onefile --windowed --name PCTweaker ^
  --icon assets\icon.ico --add-data "assets\icon.ico;assets" ^
  --collect-all customtkinter --hidden-import pythoncom --hidden-import win32com.client ^
  --hidden-import pynvml %UAC% main.py || (echo Build failed. & pause & exit /b 1)
if not exist "dist\tools" mkdir "dist\tools"
if exist "tools\*" xcopy /e /i /y "tools" "dist\tools" >nul
echo.
echo Done: dist\PCTweaker.exe
echo Keep the "tools" folder next to the exe (the app can download PresentMon and LibreHardwareMonitor into it).
pause
