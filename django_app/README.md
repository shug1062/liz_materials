# The Silver Bird · Studio (Django app)

See the [page connection map](PAGE_MAP.md) for Mermaid diagrams of the app's navigation.

## Navigation and Quick add

The app uses one shared menu. The home page is the class register: choose a
class, then a student to add materials, record payments and see all their past
purchases, newest first. The financial overview is under **Dashboard** at
`/dashboard/`, not the home page. Reports and material costs are accessible from
the shared menu; there is no separate student-facing mode.

**Students → Purchase** and **Record purchase** on a student's details page
open the same basket as **Class register → Class → Student**. Both routes offer
Quick add, material search, multiple items, payments and purchase history.
An optional **Purchase note** is saved on every item added in that basket;
payment notes remain separate. Save and Cancel return to the originating
student/class view. Existing purchases still use the individual edit form.
The main menu and Dashboard **Record purchase** links first ask you to choose
a student, then open this same basket. Saving or cancelling returns to the
chooser unless the link supplied another return destination.

**Pay cash** and **Pay card** open the payment form with the student and chosen
method selected, but no amount filled in. Both buttons remain available when
the student is settled or already in credit, for advance payments.
Enter the amount actually received and press **Save payment**.
The payment form's **£5**, **£10** and **£20–£100** (in £10 steps) shortcuts fill the amount without
saving it; you can still change the amount before confirming.
Partial payments, full payments and overpayments are supported; overpayments
remain as account credit. Cancel records nothing. The basket's payment amount
also starts blank rather than assuming the outstanding balance.
The basket and standalone payment pages use the same payment-field component,
Django form and amount-shortcut script, including the same evenly sized buttons.
The basket fixes the student to the account being viewed; the standalone form
allows choosing a student. Each keeps its existing save/return and Undo behavior.
Both require a positive amount, a valid method and a date. The date starts at
today; clearing it is a validation error rather than silently choosing today.

To change Quick add items:

1. Open **Materials** and click **Edit** beside a material.
2. Tick **Show in Quick add** to include it, or untick it to remove it.
3. Keep **Show in purchase list** ticked and save the material.

When any active materials are ticked, Quick add shows those materials. If none
are ticked, it automatically shows up to 12 active materials ranked by purchase
count (alphabetically for ties). Edit the same material to change its name,
price or unit; previous purchase prices remain unchanged.

Use **Edit section** at the top of a Materials section (such as Silver) to
edit multiple materials directly in the table. Name, pricing, pack quantity,
item weight, unit, markup and supplier details are editable; Cost each and
Student price are calculated automatically per row. **Save section** saves all
changed rows together and returns to the same section, including hidden
materials if shown. If a row is invalid, nothing is saved and errors stay in
the grid. **Cancel** discards edits in that section. Save or cancel before
editing another section.
Other settings remain unchanged and are available through each material's
**Edit** link. Grid edits use the same price history and price-date rules as
the full edit form.

## Class-wide materials

Projects linked through purchases or pending materials appear on the class
register's class page and on class details. Each Classes row also shows a
**Projects** button and named project links. Links open the corresponding
project summary. These lists include historical linked projects; payment or
material archiving does not remove a project's class association.

On **Projects**, use **Edit project & materials** to save a reusable list of
materials with optional default quantities. **Add project materials to class**
opens a review table for every active student in the chosen class.
**Add material to class** on Classes and Class register opens the same shared
Quick add/search basket as individual students, allowing several materials.
It reviews per-student quantities before saving. Archived students and sales
channels are excluded.

Older projects without defaults use previously purchased active materials
directly, with blank quantities, and identify any unavailable materials excluded
from the review. They also offer **Set up project materials** to save that
suggested list with reusable defaults. Saving returns to the class allocation.
Historical purchase quantities are never assumed to be per-student defaults.

The review grid has students down the left and materials across the top, with
explicit Weight (g), Quantity (items) or Amount (£) labels. Its **Add to all
students** row fills one material's value for every ticked student when you
press **Apply to all**, without saving. Individual values remain editable.
Adjust each student's quantity, weight or amount before saving; untick an item
to omit it. For individual silver weights, use
a material sold per gram. Blank quantities create **pending materials**, not
purchases: balances and accounting reports do not change until a quantity is
entered. Complete or remove pending items from the student's basket or details
page. Completed purchases use the current material price, retain the chosen
purchase date and project, and use the existing silver-costing rules. Saving
the class allocation, completing an item and removing an item all offer Undo.

The Class register's class page also shows a **Shared materials** grid for
materials held by at least 80% of its active students (including pending
allocations). Each student shows their quantity and Paid, Part-paid, Unpaid
or Pending status. Payments use the same oldest-purchases-first allocation
as statements, including older debts; only purchases recorded in this class
contribute to the displayed material quantities. Paid columns remain visible.
Use **Archive** to hide an individual material for this class, or **View archive**
to review and restore it. New purchases or pending allocations recorded after
archiving, or any student with a part-paid amount for that material, automatically
unarchive it when the grid is opened. It appears provided it still meets the
80% threshold. Newness uses the time the item was added, not its purchase date.
Once reopened it stays unarchived after payment is completed; you can archive
it again when no student is part-paid. Archiving does not change purchases or balances.

## Daily online prices

The first signed-in visit each day starts a background supplier-price update.
All materials with saved Cooksongold or Metal Clay links are checked, including
hidden materials; lesson fees and orders at cost are excluded. This daily run
is not limited to the manual check's 20-item batch. Valid prices and item
weights are saved automatically, with price history and today's checked date;
student prices follow the existing markup. Past purchase charges are unchanged.
The existing automatic daily silver-rate check continues separately.

A banner shows progress and the result. Offline, unsupported, invalid or
rate-limited prices stay unchanged and appear in the update details. Supplier
requests remain paced in batches of 20 with five-minute pauses between batches.
Rate-limited items get one retry after a five-minute pause; persistent failures
are reported rather than repeatedly requesting the supplier. Large lists can
take several minutes to finish. Materials edited while the check runs are not overwritten.
The daily attempt is recorded in the database so refreshing the page or
restarting the app does not repeat it. Use **Check supplier prices** on
Materials to retry failures or an interrupted run.

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
