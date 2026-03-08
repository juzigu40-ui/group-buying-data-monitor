@echo off
setlocal
cd /d %~dp0..
set "PYTHON_GUI="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_BIN=py -3"
    for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON_GUI=%%P"
    goto :run
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | find /I "WindowsApps" >nul
    if errorlevel 1 if not defined PYTHON_BIN (
      set "PYTHON_BIN=%%P"
      set "PYTHON_GUI=%%P"
    )
  )
  if defined PYTHON_BIN goto :run
)
echo Python 3 was not found on this computer.
pause
exit /b 1

:run
set "PYTHONPATH=src"
if defined PYTHON_GUI (
  set "PYTHON_GUI=%PYTHON_GUI:\python.exe=\pythonw.exe%"
  if exist "%PYTHON_GUI%" (
    start "" "%PYTHON_GUI%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
    endlocal
    exit /b 0
  )
)
if "%PYTHON_BIN%"=="py -3" (
  start "" py -3 -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
) else (
  start "" "%PYTHON_BIN%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
)
endlocal
