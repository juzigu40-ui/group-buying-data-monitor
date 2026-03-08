@echo off
setlocal EnableExtensions
set "SOURCE_DIR=%~dp0"
if "%SOURCE_DIR:~-1%"=="\" set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"
set "APP_HOME=%PUBLIC%\GBM_Runtime\shibaojie"
set "LOG_FILE=%APP_HOME%\startup.log"

if /I not "%SOURCE_DIR%"=="%APP_HOME%" (
  echo [0/5] Preparing runtime folder...
  if not exist "%APP_HOME%" mkdir "%APP_HOME%"
  robocopy "%SOURCE_DIR%" "%APP_HOME%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP /XD ".venv" "__pycache__" ".git" /XF "*.zip" >nul
  if errorlevel 8 goto COPY_FAILED
)

cd /d "%APP_HOME%"
echo start_time=%date% %time% > "%LOG_FILE%"
echo app_home=%APP_HOME% >> "%LOG_FILE%"

set "PYTHON_BIN="
set "BOOTSTRAP_CMD="

where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 --version >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
set "BOOTSTRAP_CMD=py -3"
set "PYTHON_BIN=py -3"
goto CHECK_PYTHON

:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON
set "BOOTSTRAP_CMD=python"
set "PYTHON_BIN=python"
goto CHECK_PYTHON

:NO_PYTHON
echo.
echo Python 3 was not found on this computer.
echo Please install Python 3 for Windows and check "Add Python to PATH".
echo Download: https://www.python.org/downloads/windows/
echo.
pause
exit /b 1

:CHECK_PYTHON
echo [1/5] Checking Python...
echo bootstrap=%BOOTSTRAP_CMD% >> "%LOG_FILE%"
%PYTHON_BIN% --version >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto PYTHON_FAILED

echo [2/5] Checking tkinter...
%PYTHON_BIN% -c "import tkinter" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto TK_FAILED

if not exist ".env" (
  echo [3/5] Creating local config...
  copy ".env.example" ".env" >nul
  if errorlevel 1 goto INSTALL_FAILED
)

if not exist "auth" mkdir "auth" >nul 2>nul

echo [4/5] Preparing login folder...
echo auth_dir=%APP_HOME%\auth >> "%LOG_FILE%"

echo [5/5] Launching control center...
set "PYTHONPATH=src"
%PYTHON_BIN% -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto RUN_FAILED

endlocal
exit /b 0

:COPY_FAILED
echo.
echo Failed to prepare the runtime folder.
echo Please send me a screenshot of this window.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1

:PYTHON_FAILED
echo.
echo Python check failed.
echo Please send me a screenshot of this window.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1

:INSTALL_FAILED
echo.
echo Install failed.
echo Please send me a screenshot of this window.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1

:TK_FAILED
echo.
echo Python is installed, but tkinter is missing.
echo Please reinstall official Python 3 for Windows.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1

:RUN_FAILED
echo.
echo Control center failed to start.
echo Please send me a screenshot of this window.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1
