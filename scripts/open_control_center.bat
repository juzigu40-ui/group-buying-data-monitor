@echo off
setlocal
cd /d %~dp0..
if exist .venv\Scripts\python.exe (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=python"
)
set "PYTHONPATH=src"
"%PYTHON_BIN%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
endlocal
