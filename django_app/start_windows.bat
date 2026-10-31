@echo off
rem Starts the studio tracker on this laptop so the iPad can use it on the same Wi-Fi.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)

.venv\Scripts\python manage.py migrate --noinput || goto :error
rem First run: bring across data from the old app if its database file is here.
if exist "jewelry_business.db" (
    .venv\Scripts\python manage.py import_legacy --if-empty "jewelry_business.db" || goto :error
) else if exist "..\nicegui_app\jewelry_business.db" (
    .venv\Scripts\python manage.py import_legacy --if-empty "..\nicegui_app\jewelry_business.db" || goto :error
)
.venv\Scripts\python manage.py collectstatic --noinput -v 0 || goto :error
.venv\Scripts\python manage.py backup_db

echo.
echo Open http://localhost:8000 here, or http://THIS-LAPTOP-IP:8000 on the iPad.
echo Close this window to stop the app.
.venv\Scripts\python -m waitress --listen=0.0.0.0:8000 --threads=8 studio.wsgi:application
goto :eof

:error
echo Something went wrong - see the messages above.
pause
