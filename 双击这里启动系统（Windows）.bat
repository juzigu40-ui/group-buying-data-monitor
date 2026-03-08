@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_BIN="
set "BOOTSTRAP_CMD="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
  goto INSTALL
)

where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 --version >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
set "BOOTSTRAP_CMD=py -3"
goto MAKE_VENV

:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
set "BOOTSTRAP_CMD=python"
goto MAKE_VENV

:NO_PYTHON
echo.
echo Python 3 was not found on this computer.
echo Please install Python 3 for Windows and check "Add Python to PATH".
echo Download: https://www.python.org/downloads/windows/
echo.
pause
exit /b 1

:MAKE_VENV
echo [1/5] Creating local environment...
%BOOTSTRAP_CMD% -m venv .venv
if errorlevel 1 goto INSTALL_FAILED
if not exist ".venv\Scripts\python.exe" goto INSTALL_FAILED
set "PYTHON_BIN=.venv\Scripts\python.exe"

:INSTALL
echo [2/5] Installing dependencies...
"%PYTHON_BIN%" -m pip install -U pip
if errorlevel 1 goto INSTALL_FAILED
"%PYTHON_BIN%" -m pip install -e .
if errorlevel 1 goto INSTALL_FAILED

echo [3/5] Checking tkinter...
"%PYTHON_BIN%" -c "import tkinter"
if errorlevel 1 goto TK_FAILED

if not exist ".env" (
  echo [4/5] Creating local config...
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto INSTALL_FAILED
)

echo [5/5] Launching control center...
set "PYTHONPATH=src"
"%PYTHON_BIN%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
if errorlevel 1 goto RUN_FAILED

endlocal
exit /b 0

:INSTALL_FAILED
echo.
echo Install failed.
echo Please send me a screenshot of this window.
echo.
pause
exit /b 1

:TK_FAILED
echo.
echo Python is installed, but tkinter is missing.
echo Please reinstall official Python 3 for Windows.
echo.
pause
exit /b 1

:RUN_FAILED
echo.
echo Control center failed to start.
echo Please send me a screenshot of this window.
echo.
pause
exit /b 1
