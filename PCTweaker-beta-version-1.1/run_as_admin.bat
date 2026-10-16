@echo off
REM Starts PC Tweaker elevated so every tweak, the FPS counter and sensors work.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" call setup.bat
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList 'main.py' -WorkingDirectory '%~dp0' -Verb RunAs"
