@echo off
setlocal
cd /d %~dp0..
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_BIN=py -3"
    goto :check_tk
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_BIN=python"
  goto :check_tk
)
echo python_missing=True
echo Please install Python 3 for Windows and then run this file again.
pause
exit /b 1

:check_tk
"%PYTHON_BIN%" -c "import tkinter"
if errorlevel 1 (
  echo tkinter_missing=True
  echo Please reinstall official Python 3 for Windows.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
if not exist auth mkdir auth >nul 2>nul
echo install_ready=True
echo next_step=open_control_center
pause
