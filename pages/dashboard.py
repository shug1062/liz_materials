"""Dashboard page - Main overview"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency
from silver_price_fetcher import SilverPriceFetcher

db = Database()
silver_fetcher = SilverPriceFetcher()


def dashboard_page():
    """Main dashboard page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        ui.label('Dashboard').classes('text-3xl font-bold mb-4')
        
        # Summary cards - All 5 in one row with consistent height
        summary_row = ui.row().classes('w-full max-w-6xl gap-4 mb-8')
        
        with summary_row:
            students = db.get_all_students()
            materials = db.get_all_materials()
            balances = db.get_all_student_balances()
            
            total_debt = sum(abs(b['balance']) for b in balances if b['balance'] < 0)
            total_credit = sum(b['balance'] for b in balances if b['balance'] > 0)
            
            # Summary cards - all with fixed height for consistency
            with ui.card().classes('flex-1 bg-blue-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(f'{len(students)}').classes('text-4xl font-bold text-blue-600')
                    ui.label('Total Students').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-green-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(f'{len(materials)}').classes('text-4xl font-bold text-green-600')
                    ui.label('Materials in Stock').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-red-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(format_currency(total_debt)).classes('text-4xl font-bold text-red-600')
                    ui.label('Total Outstanding Debt').classes('text-gray-600 text-center')
            
            with ui.card().classes('flex-1 bg-purple-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(format_currency(total_credit)).classes('text-4xl font-bold text-purple-600')
                    ui.label('Total Credit').classes('text-gray-600')
            
            # Silver price card - 5th card in same row with same height
            silver_card = ui.card().classes('flex-1 bg-amber-50 h-40')
            
            def refresh_silver_price():
                """Refresh the silver price display"""
                # Clear cache to force fresh fetch
                import os
                cache_file = "silver_price_cache.json"
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                
                # Re-render the entire page
                ui.navigate.to('/')
                ui.notify('Silver price updated!', type='positive')
            
            with silver_card:
                with ui.column().classes('items-center justify-center h-full'):
                    # Fetch silver price
                    silver_price = silver_fetcher.get_price()
                    
                    # Only show price if it's a real retrieved price (not fallback/estimate)
                    if silver_price and not silver_price.get('is_fallback'):
                        ui.label(f"£{silver_price['price_per_gram']:.3f}").classes('text-4xl font-bold text-amber-600')
                        ui.label('Silver Price (per gram)').classes('text-gray-600 text-sm')
                        
                        # Timestamp and refresh button
                        timestamp = datetime.fromisoformat(silver_price['timestamp'])
                        time_str = timestamp.strftime('%d/%m/%y')
                        
                        ui.label(f"Updated: {time_str}").classes('text-xs text-gray-500 mt-1')
                        
                        # Refresh button
                        ui.button('🔄 Refresh', on_click=refresh_silver_price).props('flat dense size=sm').classes('mt-1 text-xs')
                    else:
                        # Show message when price cannot be retrieved
                        ui.label('Silver Price').classes('text-xl font-bold text-amber-600')
                        ui.label('Unable to fetch price').classes('text-gray-500 text-sm mt-2')
                        ui.button('🔄 Try Again', on_click=refresh_silver_price).props('flat dense size=sm').classes('mt-2 text-xs')
        
        # Quick action buttons
        with ui.row().classes('w-full max-w-6xl gap-4 mb-8'):
            ui.button('Students', on_click=lambda: ui.navigate.to('/students')).classes('flex-1')
            ui.button('Materials', on_click=lambda: ui.navigate.to('/materials')).classes('flex-1')
            ui.button('Projects', on_click=lambda: ui.navigate.to('/projects')).classes('flex-1')
            ui.button('Record Purchase', on_click=lambda: ui.navigate.to('/purchases')).classes('flex-1')
            ui.button('Record Payment', on_click=lambda: ui.navigate.to('/payments')).classes('flex-1')
        
        # Recent activity
        with ui.card().classes('w-full max-w-6xl'):
            ui.label('Recent Purchases').classes('text-xl font-bold mb-4')
            
            purchases = db.get_all_purchases()[:10]  # Last 10 purchases
            
            if purchases:
                with ui.grid(columns=6).classes('w-full gap-2'):
                    ui.label('Date').classes('font-bold')
                    ui.label('Student').classes('font-bold')
                    ui.label('Material').classes('font-bold')
                    ui.label('Quantity').classes('font-bold')
                    ui.label('Cost').classes('font-bold')
                    ui.label('Project').classes('font-bold')
                    
                    for purchase in purchases:
                        date = datetime.fromisoformat(purchase['purchase_date']).strftime('%d/%m/%Y')
                        ui.label(date)
                        ui.label(purchase['student_name'])
                        ui.label(purchase['material_name'])
                        ui.label(f"{purchase['quantity']:.2f} {purchase['unit_type']}")
                        ui.label(format_currency(purchase['total_cost']))
                        ui.label(purchase['project_name'] or '-')
            else:
                ui.label('No purchases recorded yet').classes('text-gray-500')
