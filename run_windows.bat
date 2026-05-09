@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
%PY% --version
if errorlevel 1 (
  echo Python 3 was not found.
  pause
  exit /b 1
)
%PY% -m venv venv
call "%~dp0venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py --init-db
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
pause
