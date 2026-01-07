"""Dashboard page - Main overview"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency

db = Database()


def dashboard_page():
    """Main dashboard page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        ui.label('Dashboard').classes('text-3xl font-bold mb-4')
        
        # Summary cards
        with ui.row().classes('w-full max-w-6xl gap-4 mb-8'):
            students = db.get_all_students()
            materials = db.get_all_materials()
            balances = db.get_all_student_balances()
            
            total_debt = sum(abs(b['balance']) for b in balances if b['balance'] < 0)
            total_credit = sum(b['balance'] for b in balances if b['balance'] > 0)
            
            # Summary cards
            with ui.card().classes('flex-1 bg-blue-50'):
                ui.label(f'{len(students)}').classes('text-4xl font-bold text-blue-600')
                ui.label('Total Students').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-green-50'):
                ui.label(f'{len(materials)}').classes('text-4xl font-bold text-green-600')
                ui.label('Materials in Stock').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-red-50'):
                ui.label(format_currency(total_debt)).classes('text-4xl font-bold text-red-600')
                ui.label('Total Outstanding Debt').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-purple-50'):
                ui.label(format_currency(total_credit)).classes('text-4xl font-bold text-purple-600')
                ui.label('Total Credit').classes('text-gray-600')
        
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
