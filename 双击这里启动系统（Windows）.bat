@echo off
setlocal
cd /d %~dp0

set "PYTHON_BOOTSTRAP="
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_BOOTSTRAP=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON_BOOTSTRAP=python"
  )
)

if not defined PYTHON_BOOTSTRAP (
  echo.
  echo 未检测到 Python 3。
  echo 请先安装 Python 3（安装时勾选 Add Python to PATH），然后再双击本文件。
  echo 下载地址：https://www.python.org/downloads/windows/
  echo.
  pause
  exit /b 1
)

if not exist .venv (
  echo [1/4] 正在创建本地运行环境...
  %PYTHON_BOOTSTRAP% -m venv .venv || goto :install_failed
)

if exist .venv\Scripts\python.exe (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  echo.
  echo 本地运行环境创建失败，未找到 .venv\Scripts\python.exe
  echo.
  pause
  exit /b 1
)

echo [2/4] 正在安装依赖...
"%PYTHON_BIN%" -m pip install -U pip || goto :install_failed
"%PYTHON_BIN%" -m pip install -e . || goto :install_failed

if not exist .env (
  echo [3/4] 正在生成本地配置文件...
  copy .env.example .env >nul || goto :install_failed
)

echo [4/4] 正在启动控制台...
set "PYTHONPATH=src"
"%PYTHON_BIN%" -m gb_monitor.control_center --root-dir "%cd%" --profile-dir "data/client_profiles/shibaojie" --env-file ".env" --rules-file "data/client_profiles/shibaojie/store_signal_rules.json"
if %errorlevel% neq 0 goto :run_failed

endlocal
exit /b 0

:install_failed
echo.
echo 安装失败。请把当前窗口截图发给我，我按截图继续带你处理。
echo.
pause
exit /b 1

:run_failed
echo.
echo 控制台启动失败。常见原因是本机 Python 缺少 tkinter 组件，或安装环境不完整。
echo 请把当前窗口截图发给我，我按截图继续带你处理。
echo.
pause
exit /b 1
