@echo off
setlocal
cd /d %~dp0..
where py >nul 2>nul
if not errorlevel 1 (
  py -3 --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_BIN=py -3"
    goto :run
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_BIN=python"
  goto :run
)
echo Python 3 was not found on this computer.
pause
exit /b 1

:run
set "PYTHONPATH=src"
%PYTHON_BIN% -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
endlocal
