# Silver Jewellery Studio - Material Tracker

A comprehensive web-based dashboard for tracking student purchases, materials, and payments in your silver jewellery teaching studio.

## Features

✨ **Student Management**
- Add and manage student profiles
- Track contact information
- View complete purchase history

💎 **Materials Database**
- Store all material types with categories
- **Base price tracking** from suppliers
- **Markup percentage** for profit margin control
- **Automatic price calculation** - shows both base and final prices
- Link to supplier websites (Cooksongold integration ready)
- **🔄 One-click price updates** from supplier URLs
- Easy manual price updates

🛒 **Purchase Tracking**
- Record student purchases with **automatic cost calculation using markup**
- Link purchases to specific projects
- Track quantity by weight or item count
- View purchase history by student
- Purchases always use the final marked-up price

💰 **Payment & Balance Tracking**
- Record payments from students
- Automatic balance calculation (debt/credit)
- View outstanding balances across all students
- Payment history with methods and notes

📊 **Dashboard Overview**
- Total students and materials
- Outstanding debt and credit summary
- Recent purchase activity
- Quick navigation to all features

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup Instructions

1. **Install Required Packages**
   ```bash
   pip install nicegui requests beautifulsoup4
   ```

2. **Run the Application**
   ```bash
   python app.py
   ```

3. **Access the Dashboard**
   - Open your web browser
   - Navigate to: `http://localhost:8080`

## Usage Guide

### Adding Students
1. Go to "Students" from the dashboard
2. Click "+ Add Student"
3. Enter student details (name, email, phone, notes)
4. Click "Add Student"

### Adding Materials
1. Go to "Materials" from the dashboard
2. Click "+ Add Material"
3. Fill in material details:
   - Name (e.g., "Sterling Silver Sheet")
   - Category (e.g., "Sheet Silver", "Wire", "Gemstones")
   - Unit Type (gram, item, piece, etc.)
   - **Base Price per unit** (the cost price from supplier)
   - **Markup Percentage** (your profit margin, e.g., 20% means you charge 20% more than cost)
   - Supplier (default: Cooksongold)
   - Supplier URL (paste the full Cooksongold product page URL)
4. Click "Add Material"

**Example with Markup:**
- Base Price: £2.77 (what you pay)
- Markup: 20%
- Final Price: £3.32 (what students pay)

### Updating Prices from Cooksongold
1. Go to "Materials"
2. Find the material with a supplier URL
3. Click "🔄 Update Price" button
4. The system will automatically scrape the current price from Cooksongold
5. The base price will be updated (markup stays the same)

### Recording Purchases
1. Go to "Record Purchase" from the dashboard
2. Select the student
3. Select the material
4. Enter quantity (weight or count)
5. **The system shows:**
   - Base price (your cost)
   - Markup percentage
   - Final price per unit (what student pays)
   - Total cost is calculated automatically **using the final marked-up price**
6. Optionally link to a project
7. Click "Record Purchase"

### Recording Payments
1. Go to "Record Payment" from the dashboard
2. Select the student
3. View their current balance
4. Enter payment amount
5. Select payment method
6. Click "Record Payment"

### Viewing Student Details
1. Click on any student from the Students page
2. View tabs for:
   - **Purchases**: Complete purchase history
   - **Payments**: All payments made
   - **Projects**: Associated projects

## Database Structure

The application uses SQLite database with the following tables:
- **students**: Student profiles
- **materials**: Material inventory with pricing
- **projects**: Student projects
- **purchases**: Purchase records with costs
- **payments**: Payment records

All data is stored in `jewelry_business.db` in the same directory as the application.

## Customization

### Colors & Theme
Edit the `COLORS` dictionary in `app.py` to customize the color scheme:
```python
COLORS = {
    'primary': '#8B7355',    # Bronze/copper tone
    'secondary': '#C0C0C0',  # Silver
    'accent': '#FFD700',     # Gold
    ...
}
```

### Currency Symbol
Change the currency symbol in the `format_currency` function in `app.py`:
```python
def format_currency(amount: float) -> str:
    return f"£{amount:.2f}"  # Change £ to your currency symbol
```

## Future Enhancements

🔄 **Automatic Price Updates**
- ✅ Manual price scraping from Cooksongold (implemented!)
- Scheduled automatic price checks
- Bulk price updates for all materials
- Price history tracking
- Email notifications on price changes

📧 **Email Notifications**
- Send balance reminders to students
- Purchase receipts

📈 **Advanced Reporting**
- Monthly sales reports
- Material usage analytics
- Profit margin tracking

📱 **Mobile App**
- Responsive design improvements
- Native mobile app version

## Troubleshooting

### Port Already in Use
If port 8080 is already in use, change it in `app.py`:
```python
ui.run(title='Silver Jewellery Studio Tracker', port=8081, reload=False)
```

### Database Issues
If you encounter database errors, delete `jewelry_business.db` and restart the application to create a fresh database.

### Installation Issues
Make sure you're using Python 3.8+:
```bash
python --version
```

Update pip:
```bash
pip install --upgrade pip
```

## Support

For issues or questions:
1. Check the documentation above
2. Review the code comments in `app.py` and `database.py`
3. Ensure all dependencies are installed correctly

## License

This is a custom application for personal/business use.

---

**Built with NiceGUI** - A Python framework for creating beautiful web interfaces
