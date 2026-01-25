# 🎯 Quick Reference Card

## 🚀 Windows Deployment - 3 Simple Steps

### Step 1: Extract
Extract `jewellery_tracker_deployment.zip` to your desired location
(Example: `C:\jewellery_tracker`)

### Step 2: Run
Double-click `start_app.bat`
(First time will install everything automatically - takes 2-3 minutes)

### Step 3: Access
Open browser to: **http://localhost:8080**

---

## 🍎 macOS Quick Start

### Option A: One-click launcher (recommended)
1. Open Terminal in this folder
2. Run (first time only):
	```bash
	chmod +x start_app.command
	```
3. Double-click `start_app.command`
4. Open: **http://localhost:8080**

### Option B: Manual
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app_new.py
```

---

## 📌 Key Information

| Item | Details |
|------|---------|
| **App Size** | 36 KB (compressed) |
| **Python Required** | 3.8 or higher |
| **Internet Needed** | Only for initial setup |
| **Database Location** | `jewelry_business.db` |
| **Backup Location** | `database_backups/` folder |
| **Launcher** | `start_app.bat` (Windows) |
| **Port** | 8080 |

---

## 🔑 Essential Files

- ✅ `start_app.bat` - Click this to run the app
- ✅ `jewelry_business.db` - Your data (backup this!)
- ✅ `DEPLOYMENT_INSTRUCTIONS.md` - Full setup guide
- ✅ `requirements.txt` - Auto-installed dependencies

---

## 💾 Backup Your Data

**Automatic**: Monthly backups in `database_backups/` folder
**Manual**: Copy the entire folder to external drive/USB

---

## 🌐 Access From Other Devices

1. Find computer IP: Open Command Prompt, type `ipconfig`
2. Look for "IPv4 Address" (example: 192.168.1.100)
3. On other device, go to: `http://192.168.1.100:8080`

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Python not found | Install from python.org, check "Add to PATH" |
| Port already in use | Change port in `app_new.py` to 8081 |
| Won't start | Run as Administrator |
| Slow performance | Archive old backups |

---

## 📱 Contact/Support

- Check `DEPLOYMENT_INSTRUCTIONS.md` for detailed help
- Check `WINDOWS_SETUP.md` for Windows-specific setup
- Check `README.md` for feature documentation

---

## ✨ What's Included

✅ Student management with class grouping
✅ Material inventory with price tracking
✅ Purchase and payment recording
✅ Project cost analysis
✅ Automatic monthly backups
✅ Class name autocomplete
✅ Balance calculations
✅ Offline capable

---

**Package**: jewellery_tracker_deployment.zip
**Created**: January 7, 2026
**Status**: ✅ Ready for Windows Deployment
