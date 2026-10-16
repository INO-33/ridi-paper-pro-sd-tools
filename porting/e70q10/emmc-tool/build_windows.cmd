@echo off
cd /d "%~dp0"
py -3 build_windows.py %*
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
pause
