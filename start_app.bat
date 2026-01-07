@echo off
echo ====================================
echo Silver Jewellery Studio Tracker
echo ====================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    echo.
    echo Installing dependencies...
    call venv\Scripts\activate
    pip install -r requirements.txt
    echo.
    echo Setup complete!
    echo.
) else (
    call venv\Scripts\activate
)

echo Starting application...
echo.
echo Open your browser to: http://localhost:8080
echo.
echo Press Ctrl+C to stop the server
echo ====================================
echo.

python app_new.py

pause
