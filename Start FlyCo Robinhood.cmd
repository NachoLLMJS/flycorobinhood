@echo off
cd /d "%~dp0"
python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:4775/api/state',timeout=2);sys.exit(0 if r.status==200 else 1)" >nul 2>&1
if not errorlevel 1 (
  start "" "http://127.0.0.1:4775"
  exit /b
)
start "" "http://127.0.0.1:4775"
python server.py
pause
