# The Silver Bird · Studio (Django app)

## Navigation and Quick add

The app uses one shared menu. The home page is the class register: choose a
class, then a student to add materials, record payments and see all their past
purchases, newest first. The financial overview is under **Dashboard** at
`/dashboard/`, not the home page. Reports and material costs are accessible from
the shared menu; there is no separate student-facing mode.

To change Quick add items:

1. Open **Materials** and click **Edit** beside a material.
2. Tick **Show in Quick add** to include it, or untick it to remove it.
3. Keep **Show in purchase list** ticked and save the material.

When any active materials are ticked, Quick add shows those materials. If none
are ticked, it automatically shows up to 12 active materials ranked by purchase
count (alphabetically for ties). Edit the same material to change its name,
price or unit; previous purchase prices remain unchanged.

## Running on Windows

These steps assume Python 3.10 or newer is already installed.

### Quick start (recommended)

1. Copy or sync the whole `django_app` folder to the Windows laptop.
2. If you have data from the old app, put `jewelry_business.db` in `django_app\data\`.
3. Double-click `start_windows.bat`.
4. Optional: double-click `create_shortcut.vbs` once. It puts a **Silver Bird Studio** shortcut on the Desktop. Right-click it and choose **Pin to taskbar** (on Windows 11, choose **Show more options** first). Clicking it starts the app in a minimised window and opens the page. If the app is already running, it just opens the page.

On first run the script:

- creates a virtual environment in `django_app\.venv`
- installs the packages from `requirements.txt`
- moves the database to `%LOCALAPPDATA%\SilverBirdStudio` so OneDrive does not sync the live file
- sets up the database and imports the old data, if found
- makes a backup and starts the app

The browser opens <http://localhost:8000> once the app is ready. On the iPad, use `http://<laptop-name>:8000`; the window shows the name. Keep the window open while you use the app, and close it to stop the app.

Later runs skip package installation and start faster.

### Manual setup (if the script fails)

Open **Command Prompt** in the `django_app` folder. In File Explorer, click the address bar, type `cmd`, and press Enter.

1. Check Python:

   ```bat
   py -3 --version
   ```

   If `py` is not found, use `python` in place of `py -3` in step 2.

2. Create the virtual environment:

   ```bat
   py -3 -m venv .venv
   ```

3. Install the packages:

   ```bat
   .venv\Scripts\python -m pip install --upgrade pip
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

4. Set up the database and static files:

   ```bat
   .venv\Scripts\python manage.py relocate_data
   .venv\Scripts\python manage.py migrate --noinput
   .venv\Scripts\python manage.py import_legacy --if-empty "data\jewelry_business.db"
   .venv\Scripts\python manage.py collectstatic --noinput
   ```

   Skip `import_legacy` if you have no data from the old app.

5. Start the app:

   ```bat
   .venv\Scripts\python keep_awake_windows.py
   ```

After this, `start_windows.bat` works normally.

### Troubleshooting

- **Packages fail to install:** a work network or proxy may block pip. Try another network, or delete `.venv` and run `start_windows.bat` again.
- **The iPad cannot connect:** when Windows Firewall asks, allow Python on **Private networks**. Make sure both devices are on the same Wi-Fi and that Windows marks it as Private. If the laptop name does not work, use the laptop's IP address. Run `ipconfig`, find the IPv4 address, and open `http://<that-ip>:8000`.
- **Port 8000 is already in use:** close any other window that is running the app.
- **Start from scratch:** delete the `.venv` folder and run `start_windows.bat` again. Your data in `%LOCALAPPDATA%\SilverBirdStudio` is not affected.

### Where the data is stored

| What | Location |
|------|----------|
| Live database | `%LOCALAPPDATA%\SilverBirdStudio\studio.sqlite3` |
| Automatic backups (made on each start) | `%LOCALAPPDATA%\SilverBirdStudio\backups\` |

To copy each backup to another folder as well, such as OneDrive, set the backup folder in the app's settings. You can also set the `STUDIO_BACKUP_COPY_DIR` environment variable.

## Running on macOS

Double-click `start_mac.command`. It performs the same steps as the Windows script, using `python3`.
