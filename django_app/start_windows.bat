@echo off
rem Starts the studio tracker on this laptop so the iPad can use it on the same Wi-Fi.
cd /d "%~dp0"
set "STUDIO_HOSTNAME=%COMPUTERNAME%"
set "LOCK_DIR=%LOCALAPPDATA%\SilverBirdStudio"
if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%"

rem Windows lets a second server share port 8000, so hold this file open for as long as the window runs.
call :run 9>"%LOCK_DIR%\launcher.lock" || goto :already_started
goto :eof

:already_started
rem If the other window is still starting up, it opens the page itself.
curl -s -o nul --max-time 2 http://localhost:8000/ 2>nul && start "" http://localhost:8000/
goto :eof

:run
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv || goto :error
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)

rem The live database lives in %LOCALAPPDATA%\SilverBirdStudio, outside OneDrive; this moves it there once.
.venv\Scripts\python manage.py relocate_data || goto :error
.venv\Scripts\python manage.py migrate --noinput || goto :error
rem First run: bring across data from the old app (put jewelry_business.db in the data folder).
if exist "data\jewelry_business.db" (
    .venv\Scripts\python manage.py import_legacy --if-empty "data\jewelry_business.db" || goto :error
) else if exist "jewelry_business.db" (
    .venv\Scripts\python manage.py import_legacy --if-empty "jewelry_business.db" || goto :error
) else if exist "..\nicegui_app\jewelry_business.db" (
    .venv\Scripts\python manage.py import_legacy --if-empty "..\nicegui_app\jewelry_business.db" || goto :error
)
.venv\Scripts\python manage.py collectstatic --noinput -v 0 || goto :error
.venv\Scripts\python manage.py backup_db

echo.
echo Open http://localhost:8000 here, or try http://%COMPUTERNAME%:8000 on the iPad.
echo If the laptop name does not work on the iPad, use its Wi-Fi IP address or reserve that address in the router.
echo Close this window to stop the app.
.venv\Scripts\python keep_awake_windows.py
if errorlevel 1 goto :error
exit /b 0

:error
echo Something went wrong - see the messages above.
pause
exit /b 0
