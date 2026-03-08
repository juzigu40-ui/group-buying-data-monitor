@echo off
setlocal
cd /d %~dp0..
if not exist .venv (
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if exist .venv\Scripts\python.exe (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=python"
)
"%PYTHON_BIN%" -m pip install -U pip
"%PYTHON_BIN%" -m pip install -e .
if not exist .env copy .env.example .env >nul
echo install_ready=True
echo next_step=open_control_center
pause
