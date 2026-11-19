@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] preparing python runtime...
  if exist "runtime\python\python.exe" (
    "runtime\python\python.exe" -m venv .venv
  ) else (
    python -m venv .venv
  )
  echo [2/4] installing deps...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)
if not exist "data\runtime\index.json" (
  echo [3/4] building index...
  ".venv\Scripts\python.exe" scripts\build_index.py
)
echo [4/4] service: http://127.0.0.1:8010
start "" http://127.0.0.1:8010
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8010
