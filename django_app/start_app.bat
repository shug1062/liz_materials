@echo off
cd /d "%~dp0"

REM Check if venv exists, if not create it and install requirements
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\pip install -r requirements.txt
)

REM Run migrations and collect static files
call .venv\Scripts\python manage.py migrate --noinput
call .venv\Scripts\python manage.py collectstatic --noinput

REM Start the app in a new window
start cmd /k "cd /d "%~dp0" && .venv\Scripts\python -m waitress --listen=0.0.0.0:8000 studio.wsgi:application"

REM Wait for app to start, then open browser
timeout /t 3 /nobreak
start http://localhost:8000/sales/

exit /b 0
