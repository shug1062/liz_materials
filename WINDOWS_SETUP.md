# Windows Installation Guide

## Prerequisites
- Python 3.8 or higher installed on Windows
- Internet connection for downloading packages

## Installation Steps

### 1. Download/Copy the Project
Copy the entire project folder to your Windows laptop.

### 2. Open Command Prompt or PowerShell
Navigate to the project folder:
```cmd
cd path\to\liz_materials
```

### 3. Create a Virtual Environment (Recommended)
```cmd
python -m venv venv
```

### 4. Activate the Virtual Environment
**Command Prompt:**
```cmd
venv\Scripts\activate
```

**PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```
*Note: If you get a script execution error in PowerShell, run:*
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 5. Install Dependencies
```cmd
pip install -r requirements.txt
```

### 6. Run the Application
```cmd
python app_new.py
```

### 7. Access the Application
Open your web browser and go to:
```
http://localhost:8080
```

## Running the App Later

1. Open Command Prompt/PowerShell in the project folder
2. Activate virtual environment: `venv\Scripts\activate`
3. Run: `python app_new.py`
4. Open browser: `http://localhost:8080`

## Stopping the Application
Press `Ctrl+C` in the terminal window

## Troubleshooting

### "Python not found"
- Install Python from https://www.python.org/downloads/
- Make sure to check "Add Python to PATH" during installation

### "Module not found" errors
- Make sure virtual environment is activated
- Re-run: `pip install -r requirements.txt`

### Port 8080 already in use
- Change the port in `app_new.py` line 55:
  ```python
  ui.run(title='Silver Jewellery Studio Tracker', port=8081, reload=False)
  ```

### Database file not found
- The database file `jewelry_business.db` will be created automatically on first run
- Keep this file - it contains all your data!

## Files to Keep Safe
- `jewelry_business.db` - Your database (contains all data)
- `database_backups/` folder - Automatic monthly backups (NEW!)
- All `.py` files - Your application code
- `requirements.txt` - Dependencies list

## 🔄 Automatic Backups (NEW!)
The app now creates automatic monthly backups:
- Backups created in `database_backups/` folder
- Happens automatically on app startup if 30+ days since last backup
- Keeps 12 most recent backups (1 year)
- See `BACKUP_SYSTEM.md` for full details

## Optional: Create a Windows Batch File for Easy Launch

Create a file called `start_app.bat` with this content:
```batch
@echo off
call venv\Scripts\activate
python app_new.py
pause
```

Then just double-click `start_app.bat` to start the application!
