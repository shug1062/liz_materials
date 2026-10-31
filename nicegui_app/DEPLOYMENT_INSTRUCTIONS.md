# 🚀 Silver Jewellery Studio Tracker - Deployment Guide

## 📦 What's Included
- Complete application code
- Database with automatic backup system
- Windows launcher (start_app.bat)
- All documentation

## 🖥️ Windows Installation

### Prerequisites
- Windows 10 or 11
- Python 3.8 or higher ([Download from python.org](https://www.python.org/downloads/))
  - ⚠️ **Important**: Check "Add Python to PATH" during installation

### Quick Start (Recommended)
1. **Extract the ZIP file** to a folder (e.g., `C:\jewellery_tracker`)
2. **Double-click `start_app.bat`**
3. The first run will:
   - Create a virtual environment
   - Install all dependencies automatically
   - Start the application
4. **Open your browser** to: http://localhost:8080
5. Done! 🎉

### Manual Installation (Alternative)
If the batch file doesn't work:

1. Open Command Prompt in the extracted folder
2. Run these commands:
   ```cmd
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python app_new.py
   ```
3. Open browser to: http://localhost:8080

## 🍎 macOS Installation

### One-click (recommended)
1. Open Terminal in the extracted folder
2. Run (first time only):
   ```bash
   chmod +x start_app.command
   ```
3. Double-click `start_app.command`
4. Open your browser to: http://localhost:8080

### Manual
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app_new.py
```

## 📱 Accessing from Other Devices
Once running, access from:
- Same computer: http://localhost:8080
- Other devices on same network: http://YOUR_COMPUTER_IP:8080
  - Find your IP: Run `ipconfig` in Command Prompt, look for IPv4 Address

## 📂 Important Files
- `start_app.bat` - One-click launcher for Windows
- `app_new.py` - Main application file
- `jewelry_business.db` - Your database (contains all data)
- `database_backups/` - Automatic monthly backups
- `requirements.txt` - Python dependencies

## 💾 Backup System
- **Automatic**: Creates monthly backups in `database_backups/` folder
- **Manual**: Copy the entire folder to backup everything
- **Database only**: Copy `jewelry_business.db` file

## 🔧 Features Included
✅ Student management with class grouping
✅ Material inventory tracking with price updates
✅ Purchase recording and editing
✅ Payment tracking
✅ Project management with cost analysis
✅ Balance calculations
✅ Automatic monthly database backups
✅ Class name autocomplete
✅ Average cost per student for projects

## 🆘 Troubleshooting

### "Python not found"
- Install Python from python.org
- Make sure to check "Add Python to PATH"
- Restart computer after installation

### Port 8080 already in use
- Edit `app_new.py`, change line: `ui.run(port=8080)` to `ui.run(port=8081)`

### Application won't start
- Make sure no antivirus is blocking Python
- Run Command Prompt as Administrator
- Check Python version: `python --version` (should be 3.8+)

## 📞 Support
For issues or questions, refer to:
- `WINDOWS_SETUP.md` - Detailed Windows setup guide
- `README.md` - Application features and usage

## 🔄 Updates
To update the application:
1. Backup your `jewelry_business.db` file
2. Extract new version to a different folder
3. Copy your old `jewelry_business.db` to the new folder
4. Run `start_app.bat`

## ⚠️ Data Safety
- Your database is in `jewelry_business.db`
- Backups are automatically created monthly in `database_backups/`
- Always keep backups before major changes
- The application works offline - no internet required for core features

---
**Created**: January 2026
**Version**: 1.0
**Platform**: Cross-platform (Windows, macOS, Linux)
