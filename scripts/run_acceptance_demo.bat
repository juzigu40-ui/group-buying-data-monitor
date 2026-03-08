@echo off
setlocal
cd /d %~dp0..
if exist .venv\Scripts\python.exe (
  set "PYTHON_BIN=.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=python"
)
set "PYTHONPATH=src"
"%PYTHON_BIN%" -m gb_monitor.cli profile-readiness --profile-dir "data/client_profiles/shibaojie" --require-feishu || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli feishu-ping || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli init-db || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli validate-registry --registry "data/client_profiles/shibaojie/stores_registry.json" || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli run --mode all || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli report --hours 24 || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli profile-deliverable --profile-dir "data/client_profiles/shibaojie" --output "data/client_profiles/shibaojie/single_store_deliverable.md" || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli profile-signals --profile-dir "data/client_profiles/shibaojie" --mode all --notify --mark-dispatched --board-output "data/client_profiles/shibaojie/signal_watchboard.md" --report-output "data/client_profiles/shibaojie/signal_report.txt" || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli profile-signal-deliverable --profile-dir "data/client_profiles/shibaojie" --output "data/client_profiles/shibaojie/signal_delivery_explainer.md" || goto :end
"%PYTHON_BIN%" -m gb_monitor.cli profile-usage-guide --profile-dir "data/client_profiles/shibaojie" --output "data/client_profiles/shibaojie/client_usage_guide.md"
:end
pause
