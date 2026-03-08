@echo off
setlocal EnableExtensions
set "SOURCE_DIR=%~dp0"
if "%SOURCE_DIR:~-1%"=="\" set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"
set "APP_HOME=%PUBLIC%\GBM_Runtime\shibaojie"
set "LOG_FILE=%APP_HOME%\startup.log"
set "PYTHON_BIN="
set "PYTHON_DESC="
set "PYTHON_GUI="

if /I not "%SOURCE_DIR%"=="%APP_HOME%" (
  echo [0/5] Preparing runtime folder...
  if not exist "%APP_HOME%" mkdir "%APP_HOME%"
  robocopy "%SOURCE_DIR%" "%APP_HOME%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP /XD ".venv" "__pycache__" ".git" /XF "*.zip" >nul
  if errorlevel 8 goto COPY_FAILED
)

cd /d "%APP_HOME%"
echo start_time=%date% %time% > "%LOG_FILE%"
echo app_home=%APP_HOME% >> "%LOG_FILE%"

:CHECK_PYTHON
echo [1/5] Checking Python...
call :detect_python
if errorlevel 1 goto NO_PYTHON
echo python=%PYTHON_DESC% >> "%LOG_FILE%"

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
if defined PYTHON_GUI if exist "%PYTHON_GUI%" (
  start "" "%PYTHON_GUI%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
  endlocal
  exit /b 0
)
if "%PYTHON_BIN%"=="py -3" (
  start "" py -3 -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
) else (
  start "" "%PYTHON_BIN%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
)
endlocal
exit /b 0

:detect_python
py -3 -c "import sys; print(sys.executable)" > "%APP_HOME%\python_path.txt" 2>> "%LOG_FILE%"
if not errorlevel 1 (
  set /p DETECTED_PY=<"%APP_HOME%\python_path.txt"
  del "%APP_HOME%\python_path.txt" >nul 2>nul
  set "PYTHON_BIN=py -3"
  set "PYTHON_DESC=%DETECTED_PY%"
  set "PYTHON_GUI=%DETECTED_PY:\python.exe=\pythonw.exe%"
  exit /b 0
)
del "%APP_HOME%\python_path.txt" >nul 2>nul

for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | find /I "WindowsApps" >nul
  if errorlevel 1 (
    "%%P" -c "import sys; print(sys.executable)" > "%APP_HOME%\python_path.txt" 2>> "%LOG_FILE%"
    if not errorlevel 1 (
      set /p DETECTED_PY=<"%APP_HOME%\python_path.txt"
      del "%APP_HOME%\python_path.txt" >nul 2>nul
      set "PYTHON_BIN=%%P"
      set "PYTHON_DESC=%DETECTED_PY%"
      set "PYTHON_GUI=%DETECTED_PY:\python.exe=\pythonw.exe%"
      exit /b 0
    )
    del "%APP_HOME%\python_path.txt" >nul 2>nul
  )
)
exit /b 1

:COPY_FAILED
echo.
echo Failed to prepare the runtime folder.
echo Please send me a screenshot of this window.
echo Log file: %LOG_FILE%
echo.
pause
exit /b 1

:NO_PYTHON
echo.
echo Python 3 was not found on this computer.
echo Please install official Python 3 for Windows first.
echo Download: https://www.python.org/downloads/windows/
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
