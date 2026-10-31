"""Dashboard page - Main overview"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency
from silver_price_fetcher import SilverPriceFetcher
from urllib.parse import quote
import os

db = Database()
silver_fetcher = SilverPriceFetcher()


def dashboard_page():
    """Main dashboard page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        ui.label('Dashboard').classes('text-3xl font-bold mb-4')
        
        # Summary cards - All 5 in one row with consistent height
        summary_row = ui.row().classes('w-full max-w-6xl gap-4 mb-4')
        
        with summary_row:
            students = db.get_all_students()
            materials = db.get_all_materials()
            balances = db.get_all_student_balances()
            
            # Separate regular students from sales channels
            regular_students = [s for s in students if not s.get('is_sales_channel')]
            sales_channels = [s for s in students if s.get('is_sales_channel')]
            
            # Calculate class sales (excluding sales channels)
            class_debt = 0
            class_credit = 0
            for balance in balances:
                student = db.get_student(balance['student_id'])
                if not student.get('is_sales_channel'):
                    if balance['balance'] < 0:
                        class_debt += abs(balance['balance'])
                    elif balance['balance'] > 0:
                        class_credit += balance['balance']
            
            # Get all payments and calculate cash/card totals for classes only (exclude sales channels)
            all_payments = db.get_all_payments()
            sales_channel_ids = [c['id'] for c in sales_channels]
            
            # Filter out sales channel payments for class summary
            class_payments = [p for p in all_payments if p.get('student_id') not in sales_channel_ids]
            
            cash_total = sum(
                float(p.get('amount') or 0)
                for p in class_payments
                if (p.get('payment_method') or '').strip().lower() == 'cash'
            )
            card_total = sum(
                float(p.get('amount') or 0)
                for p in class_payments
                if (p.get('payment_method') or '').strip().lower() == 'card'
            )
            
            # Payment summary card - classes only
            with ui.card().classes('flex-1 bg-blue-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center gap-1'):
                    ui.label('Class Payment Summary').classes('text-sm font-bold text-blue-600 mb-1')
                    with ui.row().classes('gap-4'):
                        with ui.column().classes('items-center'):
                            ui.label(format_currency(cash_total)).classes('text-2xl font-bold text-blue-700')
                            ui.label('Cash').classes('text-xs text-gray-600')
                        with ui.column().classes('items-center'):
                            ui.label(format_currency(card_total)).classes('text-2xl font-bold text-blue-700')
                            ui.label('Card').classes('text-xs text-gray-600')
            
            with ui.card().classes('flex-1 bg-green-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(f'{len(materials)}').classes('text-4xl font-bold text-green-600')
                    ui.label('Materials in Stock').classes('text-gray-600')
            
            with ui.card().classes('flex-1 bg-red-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(format_currency(class_debt)).classes('text-4xl font-bold text-red-600')
                    ui.label('Class Debt').classes('text-gray-600 text-center')
            
            with ui.card().classes('flex-1 bg-purple-50 h-40 flex items-center justify-center'):
                with ui.column().classes('items-center'):
                    ui.label(format_currency(class_credit)).classes('text-4xl font-bold text-purple-600')
                    ui.label('Class Credit').classes('text-gray-600')
            
            # Silver price card - 5th card in same row with same height
            silver_card = ui.card().classes('flex-1 bg-amber-50 h-40')

            def _render_silver_content(container: ui.column):
                container.clear()
                with container:
                    # Fetch silver price (cached or fresh)
                    silver_price = silver_fetcher.get_price()

                    if silver_price and not silver_price.get('is_fallback'):
                        ui.label(f"£{silver_price['price_per_gram']:.3f}").classes('text-4xl font-bold text-amber-600')
                        ui.label('Silver Price (per gram)').classes('text-gray-600 text-sm')

                        timestamp = datetime.fromisoformat(silver_price['timestamp'])
                        time_str = timestamp.strftime('%d/%m/%y')
                        ui.label(f"Updated: {time_str}").classes('text-xs text-gray-500 mt-1')

                        ui.button('🔄 Refresh', on_click=lambda: refresh_silver_price(force=True)).props('flat dense size=sm').classes('mt-1 text-xs')
                    else:
                        ui.label('Silver Price').classes('text-xl font-bold text-amber-600')
                        ui.label('Unable to fetch price').classes('text-gray-500 text-sm mt-2')
                        ui.button('🔄 Try Again', on_click=lambda: refresh_silver_price(force=True)).props('flat dense size=sm').classes('mt-2 text-xs')

            def refresh_silver_price(force: bool = False, notify: bool = False):
                """Refresh the silver price display.

                - force=True clears cache and fetches fresh
                - notify=True shows a success toast
                """
                if force:
                    cache_file = "silver_price_cache.json"
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                _render_silver_content(silver_content)
                if notify:
                    ui.notify('Silver price updated!', type='positive')
            
            with silver_card:
                with ui.column().classes('items-center justify-center h-full'):
                    silver_content = ui.column().classes('items-center justify-center h-full')
                    _render_silver_content(silver_content)

                    def _auto_refresh_if_needed():
                        # If cache isn't valid for today, refresh the card.
                        if silver_fetcher.get_cached_price() is None:
                            refresh_silver_price(force=False, notify=False)

                    # Check hourly while the dashboard is open.
                    ui.timer(60 * 60, _auto_refresh_if_needed)
        
        # Sales Channels Summary section
        if sales_channels:
            with ui.card().classes('w-full max-w-6xl mb-4 bg-gradient-to-r from-teal-50 to-cyan-50'):
                ui.label('Sales Channels Summary').classes('text-xl font-bold mb-4')
                
                # Calculate combined totals
                combined_cash = 0
                combined_card = 0
                combined_total = 0
                
                channel_data = []
                for channel in sales_channels:
                    # Get all payments for this channel
                    channel_payments = db.get_all_payments(student_id=channel['id'])
                    cash_total = sum(
                        float(p.get('amount') or 0)
                        for p in channel_payments
                        if (p.get('payment_method') or '').strip().lower() == 'cash'
                    )
                    card_total = sum(
                        float(p.get('amount') or 0)
                        for p in channel_payments
                        if (p.get('payment_method') or '').strip().lower() == 'card'
                    )
                    total = cash_total + card_total
                    
                    combined_cash += cash_total
                    combined_card += card_total
                    combined_total += total
                    
                    channel_data.append({
                        'name': channel['name'],
                        'cash': cash_total,
                        'card': card_total,
                        'total': total
                    })
                
                # Display all channels in a single row
                with ui.row().classes('w-full gap-2'):
                    for data in channel_data:
                        with ui.card().classes('flex-1 bg-white'):
                            with ui.column().classes('items-center justify-start pt-1 px-2 pb-2 gap-0'):
                                ui.label(data['name']).classes('text-xs font-bold text-teal-700 mb-1')
                                ui.label(f"Cash: {format_currency(data['cash'])}").classes('text-xs text-gray-600')
                                ui.label(f"Card: {format_currency(data['card'])}").classes('text-xs text-gray-600')
                                ui.label(f"Total: {format_currency(data['total'])}").classes('text-xs font-bold text-teal-600')
                    
                    # Combined total card
                    with ui.card().classes('flex-1 bg-teal-100'):
                        with ui.column().classes('items-center justify-start pt-1 px-2 pb-2 gap-0'):
                            ui.label('Combined').classes('text-xs font-bold text-teal-800 mb-1')
                            ui.label(f"Cash: {format_currency(combined_cash)}").classes('text-xs text-gray-700')
                            ui.label(f"Card: {format_currency(combined_card)}").classes('text-xs text-gray-700')
                            ui.label(f"Total: {format_currency(combined_total)}").classes('text-xs font-bold text-teal-700')
        
        # Class buttons section
        with ui.card().classes('w-full max-w-6xl'):
            ui.label('Classes').classes('text-xl font-bold mb-4')
            
            # Get all classes
            ordered_classes = db.get_ordered_classes()
            
            if ordered_classes:
                with ui.row().classes('w-full gap-2 flex-wrap'):
                    for class_name in ordered_classes:
                        # Get students count for this class
                        all_students = db.get_all_students()
                        students_in_class = [s for s in all_students if s.get('class_name') == class_name]
                        count = len(students_in_class)
                        
                        # Create button with class name and student count
                        # Encode the class name for URL
                        encoded_name = quote(class_name)
                        ui.button(
                            f"{class_name} ({count})",
                            on_click=lambda en=encoded_name: ui.navigate.to(f'/students?class_name={en}')
                        ).props('outline').classes('flex-grow')
            else:
                ui.label('No classes created yet').classes('text-gray-500')
        
        # Quick action buttons
        with ui.row().classes('w-full max-w-6xl gap-4 mb-8'):
            ui.button('Students', on_click=lambda: ui.navigate.to('/students')).classes('flex-1')
            ui.button('Materials', on_click=lambda: ui.navigate.to('/materials')).classes('flex-1')
            ui.button('Projects', on_click=lambda: ui.navigate.to('/projects')).classes('flex-1')
            ui.button('Record Purchase', on_click=lambda: ui.navigate.to('/purchases')).classes('flex-1')
            ui.button('Record Payment', on_click=lambda: ui.navigate.to('/payments')).classes('flex-1')
            ui.button('View Class Payments', on_click=lambda: ui.navigate.to('/payments_report?filter=class')).classes('flex-1')
            ui.button('View Sales', on_click=lambda: ui.navigate.to('/payments_report?filter=sales')).classes('flex-1')
        
        # Recent activity with tabs
        with ui.card().classes('w-full max-w-6xl'):
            ui.label('Recent Activity').classes('text-xl font-bold mb-4')
            
            with ui.tabs().classes('w-full') as tabs:
                purchases_tab = ui.tab('Recent Purchases')
                payments_tab = ui.tab('Recent Class Payments')
                cash_tab = ui.tab('Recent Class Cash Payments')
                sales_tab = ui.tab('Recent Sales')
            
            with ui.tab_panels(tabs, value=purchases_tab).classes('w-full'):
                # Recent Purchases tab
                with ui.tab_panel(purchases_tab):
                    purchases = db.get_all_purchases()[:10]  # Last 10 purchases
                    
                    if purchases:
                        with ui.grid(columns=8).classes('w-full gap-2'):
                            ui.label('Date').classes('font-bold')
                            ui.label('Student').classes('font-bold')
                            ui.label('Material').classes('font-bold')
                            ui.label('Quantity').classes('font-bold')
                            ui.label('Cost').classes('font-bold')
                            ui.label('Project').classes('font-bold')
                            ui.label('Actions').classes('font-bold')
                            ui.label('')  # Empty cell for layout
                            
                            for purchase in purchases:
                                purchase_date = datetime.fromisoformat(purchase['purchase_date']).strftime('%d/%m/%Y')
                                ui.label(purchase_date)
                                ui.label(purchase['student_name'])
                                ui.label(purchase['material_name'])
                                ui.label(f"{purchase['quantity']:.2f} {purchase['unit_type']}")
                                ui.label(format_currency(purchase['total_cost']))
                                ui.label(purchase['project_name'] or '-')
                                
                                # Action buttons
                                def create_edit_purchase_handler(p):
                                    def edit_handler():
                                        with ui.dialog() as edit_dialog, ui.card().classes('w-96'):
                                            ui.label('Edit Purchase').classes('text-xl font-bold mb-4')
                                            
                                            # Get fresh data
                                            students = db.get_all_students()
                                            materials = db.get_active_materials()
                                            projects = db.get_all_projects()
                                            
                                            purchase_date_str = p.get('purchase_date') or ''
                                            try:
                                                date_value = datetime.fromisoformat(purchase_date_str.split(' ')[0]).strftime('%Y-%m-%d')
                                            except Exception:
                                                date_value = str(date.today())
                                            
                                            date_input = ui.input('Date *', value=date_value).props('type=date').classes('w-full')
                                            
                                            student_options = {s['name']: s['id'] for s in students}
                                            current_student = next((s['name'] for s in students if s['id'] == p['student_id']), '')
                                            student_select = ui.select(list(student_options.keys()), label='Student *', value=current_student).classes('w-full')
                                            
                                            material_options = {m['name']: m['id'] for m in materials}
                                            current_material = next((m['name'] for m in materials if m['id'] == p['material_id']), '')
                                            material_select = ui.select(list(material_options.keys()), label='Material *', value=current_material).classes('w-full')
                                            
                                            quantity_input = ui.number('Quantity *', min=0.01, step=0.01, precision=2, value=float(p.get('quantity') or 0)).classes('w-full')
                                            
                                            project_options = {'None': None}
                                            project_options.update({proj['name']: proj['id'] for proj in projects})
                                            current_project = 'None'
                                            if p.get('project_id'):
                                                current_project = next((proj['name'] for proj in projects if proj['id'] == p['project_id']), 'None')
                                            project_select = ui.select(list(project_options.keys()), label='Project', value=current_project).classes('w-full')
                                            
                                            notes_input = ui.textarea('Notes', value=p.get('notes') or '').classes('w-full')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                                                
                                                def update_purchase():
                                                    if not student_select.value or not material_select.value or not quantity_input.value or quantity_input.value <= 0:
                                                        ui.notify('Please fill in all required fields', type='warning')
                                                        return
                                                    
                                                    try:
                                                        db.update_purchase(
                                                            purchase_id=p['id'],
                                                            student_id=student_options[student_select.value],
                                                            material_id=material_options[material_select.value],
                                                            quantity=quantity_input.value,
                                                            project_id=project_options[project_select.value],
                                                            notes=notes_input.value or '',
                                                            purchase_date=date_input.value
                                                        )
                                                        ui.notify('Purchase updated successfully', type='positive')
                                                        edit_dialog.close()
                                                        ui.navigate.to('/')
                                                    except Exception as e:
                                                        ui.notify(f'Failed to update purchase: {str(e)}', type='negative')
                                                
                                                ui.button('Update', on_click=update_purchase)
                                        
                                        edit_dialog.open()
                                    return edit_handler
                                
                                def create_delete_purchase_handler(p):
                                    def delete_handler():
                                        with ui.dialog() as delete_dialog, ui.card().classes('w-96'):
                                            ui.label('Delete Purchase?').classes('text-xl font-bold mb-4')
                                            ui.label(f"Student: {p.get('student_name') or 'Unknown'}").classes('text-gray-600')
                                            ui.label(f"Material: {p.get('material_name') or 'Unknown'}").classes('text-gray-600')
                                            ui.label(f"Quantity: {p.get('quantity'):.2f} {p.get('unit_type')}").classes('text-gray-600')
                                            ui.label(f"Cost: {format_currency(p.get('total_cost'))}").classes('text-gray-600 font-bold')
                                            ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=delete_dialog.close).props('flat')
                                                
                                                def confirm_delete():
                                                    try:
                                                        db.delete_purchase(p['id'])
                                                        ui.notify('Purchase deleted successfully', type='positive')
                                                        delete_dialog.close()
                                                        ui.navigate.to('/')
                                                    except Exception as e:
                                                        ui.notify(f'Failed to delete purchase: {str(e)}', type='negative')
                                                
                                                ui.button('Delete', on_click=confirm_delete).props('color=red')
                                        
                                        delete_dialog.open()
                                    return delete_handler
                                
                                with ui.row().classes('gap-1'):
                                    ui.button('✏️', on_click=create_edit_purchase_handler(purchase)).props('flat dense color=blue').classes('text-sm')
                                    ui.button('🗑', on_click=create_delete_purchase_handler(purchase)).props('flat dense color=red').classes('text-sm')
                                ui.label('')  # Empty cell for layout
                    else:
                        ui.label('No purchases recorded yet').classes('text-gray-500')
                
                # Recent Class Payments tab (exclude sales channels)
                with ui.tab_panel(payments_tab):
                    # Get only class payments (exclude sales channels)
                    sales_channel_ids = [c['id'] for c in sales_channels]
                    class_only_payments = [p for p in all_payments if p.get('student_id') not in sales_channel_ids][:10]
                    
                    if class_only_payments:
                        with ui.grid(columns=7).classes('w-full gap-2'):
                            ui.label('Date').classes('font-bold')
                            ui.label('Student').classes('font-bold')
                            ui.label('Amount').classes('font-bold')
                            ui.label('Method').classes('font-bold')
                            ui.label('Notes').classes('font-bold')
                            ui.label('Actions').classes('font-bold')
                            ui.label('')  # Empty cell for layout
                            
                            for payment in class_only_payments:
                                raw_date = payment.get('payment_date') or ''
                                try:
                                    shown_date = datetime.fromisoformat(raw_date).strftime('%d/%m/%Y')
                                except Exception:
                                    shown_date = raw_date
                                
                                ui.label(shown_date)
                                ui.label(payment.get('student_name') or '')
                                ui.label(format_currency(float(payment.get('amount') or 0))).classes('font-bold text-green-700')
                                ui.label(payment.get('payment_method') or '-')
                                ui.label(payment.get('notes') or '-')
                                
                                # Action buttons
                                def create_edit_handler(p):
                                    def edit_handler():
                                        with ui.dialog() as edit_dialog, ui.card().classes('w-96'):
                                            ui.label('Edit Payment').classes('text-xl font-bold mb-4')
                                            
                                            payment_date_str = p.get('payment_date') or ''
                                            try:
                                                date_value = datetime.fromisoformat(payment_date_str.split(' ')[0]).strftime('%Y-%m-%d')
                                            except Exception:
                                                date_value = str(date.today())
                                            
                                            date_input = ui.input('Date *', value=date_value).props('type=date').classes('w-full')
                                            amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2, value=float(p.get('amount') or 0)).classes('w-full')
                                            method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                                                    label='Payment Method', value=p.get('payment_method') or '').classes('w-full')
                                            notes_input = ui.textarea('Notes', value=p.get('notes') or '').classes('w-full')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                                                
                                                def update_payment():
                                                    if not amount_input.value or amount_input.value <= 0:
                                                        ui.notify('Please enter a valid amount', type='warning')
                                                        return
                                                    
                                                    if db.update_payment(
                                                        payment_id=p['id'],
                                                        amount=amount_input.value,
                                                        payment_method=method_input.value or '',
                                                        notes=notes_input.value or '',
                                                        payment_date=date_input.value
                                                    ):
                                                        ui.notify('Payment updated successfully', type='positive')
                                                        edit_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to update payment', type='negative')
                                                
                                                ui.button('Update', on_click=update_payment)
                                        
                                        edit_dialog.open()
                                    return edit_handler
                                
                                def create_delete_handler(p):
                                    def delete_handler():
                                        with ui.dialog() as delete_dialog, ui.card().classes('w-96'):
                                            ui.label('Delete Payment?').classes('text-xl font-bold mb-4')
                                            ui.label(f"Student: {p.get('student_name') or 'Unknown'}").classes('text-gray-600')
                                            ui.label(f"Amount: {format_currency(float(p.get('amount') or 0))}").classes('text-gray-600 font-bold')
                                            ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=delete_dialog.close).props('flat')
                                                
                                                def confirm_delete():
                                                    if db.delete_payment(p['id']):
                                                        ui.notify('Payment deleted successfully', type='positive')
                                                        delete_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to delete payment', type='negative')
                                                
                                                ui.button('Delete', on_click=confirm_delete).props('color=red')
                                        
                                        delete_dialog.open()
                                    return delete_handler
                                
                                with ui.row().classes('gap-1'):
                                    ui.button('✏️', on_click=create_edit_handler(payment)).props('flat dense color=blue').classes('text-sm')
                                    ui.button('🗑', on_click=create_delete_handler(payment)).props('flat dense color=red').classes('text-sm')
                                ui.label('')  # Empty cell for layout
                    else:
                        ui.label('No class payments recorded yet').classes('text-gray-500')
                
                # Recent Class Cash Payments tab (exclude sales channels)
                with ui.tab_panel(cash_tab):
                    # Get only class cash payments (exclude sales channels)
                    sales_channel_ids = [c['id'] for c in sales_channels]
                    all_payments_list = db.get_all_payments()
                    cash_payments = [
                        p for p in all_payments_list 
                        if (p.get('payment_method') or '').strip().lower() == 'cash' 
                        and p.get('student_id') not in sales_channel_ids
                    ][:10]
                    
                    if cash_payments:
                        with ui.grid(columns=6).classes('w-full gap-2'):
                            ui.label('Date').classes('font-bold')
                            ui.label('Student').classes('font-bold')
                            ui.label('Amount').classes('font-bold')
                            ui.label('Notes').classes('font-bold')
                            ui.label('Actions').classes('font-bold')
                            ui.label('')  # Empty cell for layout
                            
                            for payment in cash_payments:
                                raw_date = payment.get('payment_date') or ''
                                try:
                                    shown_date = datetime.fromisoformat(raw_date).strftime('%d/%m/%Y')
                                except Exception:
                                    shown_date = raw_date
                                
                                ui.label(shown_date)
                                ui.label(payment.get('student_name') or '')
                                ui.label(format_currency(float(payment.get('amount') or 0))).classes('font-bold text-green-700')
                                ui.label(payment.get('notes') or '-')
                                
                                # Action buttons
                                def create_edit_handler_cash(p):
                                    def edit_handler():
                                        with ui.dialog() as edit_dialog, ui.card().classes('w-96'):
                                            ui.label('Edit Payment').classes('text-xl font-bold mb-4')
                                            
                                            payment_date_str = p.get('payment_date') or ''
                                            try:
                                                date_value = datetime.fromisoformat(payment_date_str.split(' ')[0]).strftime('%Y-%m-%d')
                                            except Exception:
                                                date_value = str(date.today())
                                            
                                            date_input = ui.input('Date *', value=date_value).props('type=date').classes('w-full')
                                            amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2, value=float(p.get('amount') or 0)).classes('w-full')
                                            method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                                                    label='Payment Method', value=p.get('payment_method') or '').classes('w-full')
                                            notes_input = ui.textarea('Notes', value=p.get('notes') or '').classes('w-full')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                                                
                                                def update_payment():
                                                    if not amount_input.value or amount_input.value <= 0:
                                                        ui.notify('Please enter a valid amount', type='warning')
                                                        return
                                                    
                                                    if db.update_payment(
                                                        payment_id=p['id'],
                                                        amount=amount_input.value,
                                                        payment_method=method_input.value or '',
                                                        notes=notes_input.value or '',
                                                        payment_date=date_input.value
                                                    ):
                                                        ui.notify('Payment updated successfully', type='positive')
                                                        edit_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to update payment', type='negative')
                                                
                                                ui.button('Update', on_click=update_payment)
                                        
                                        edit_dialog.open()
                                    return edit_handler
                                
                                def create_delete_handler_cash(p):
                                    def delete_handler():
                                        with ui.dialog() as delete_dialog, ui.card().classes('w-96'):
                                            ui.label('Delete Payment?').classes('text-xl font-bold mb-4')
                                            ui.label(f"Student: {p.get('student_name') or 'Unknown'}").classes('text-gray-600')
                                            ui.label(f"Amount: {format_currency(float(p.get('amount') or 0))}").classes('text-gray-600 font-bold')
                                            ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=delete_dialog.close).props('flat')
                                                
                                                def confirm_delete():
                                                    if db.delete_payment(p['id']):
                                                        ui.notify('Payment deleted successfully', type='positive')
                                                        delete_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to delete payment', type='negative')
                                                
                                                ui.button('Delete', on_click=confirm_delete).props('color=red')
                                        
                                        delete_dialog.open()
                                    return delete_handler
                                
                                with ui.row().classes('gap-1'):
                                    ui.button('✏️', on_click=create_edit_handler_cash(payment)).props('flat dense color=blue').classes('text-sm')
                                    ui.button('🗑', on_click=create_delete_handler_cash(payment)).props('flat dense color=red').classes('text-sm')
                                ui.label('')  # Empty cell for layout
                    else:
                        ui.label('No class cash payments recorded yet').classes('text-gray-500')
                
                # Recent Sales tab (payments to sales channels)
                with ui.tab_panel(sales_tab):
                    # Get payments only for sales channels
                    sales_channel_ids = [c['id'] for c in sales_channels]
                    sales_payments = [p for p in all_payments if p.get('student_id') in sales_channel_ids][:10]
                    
                    if sales_payments:
                        with ui.grid(columns=7).classes('w-full gap-2'):
                            ui.label('Date').classes('font-bold')
                            ui.label('Channel').classes('font-bold')
                            ui.label('Amount').classes('font-bold')
                            ui.label('Method').classes('font-bold')
                            ui.label('Notes').classes('font-bold')
                            ui.label('Actions').classes('font-bold')
                            ui.label('')  # Empty cell for layout
                            
                            for payment in sales_payments:
                                raw_date = payment.get('payment_date') or ''
                                try:
                                    shown_date = datetime.fromisoformat(raw_date).strftime('%d/%m/%Y')
                                except Exception:
                                    shown_date = raw_date
                                
                                ui.label(shown_date)
                                ui.label(payment.get('student_name') or '').classes('text-teal-700 font-semibold')
                                ui.label(format_currency(float(payment.get('amount') or 0))).classes('font-bold text-green-700')
                                ui.label(payment.get('payment_method') or '-')
                                ui.label(payment.get('notes') or '-')
                                
                                # Action buttons
                                def create_edit_handler_sales(p):
                                    def edit_handler():
                                        with ui.dialog() as edit_dialog, ui.card().classes('w-96'):
                                            ui.label('Edit Sale').classes('text-xl font-bold mb-4')
                                            
                                            payment_date_str = p.get('payment_date') or ''
                                            try:
                                                date_value = datetime.fromisoformat(payment_date_str.split(' ')[0]).strftime('%Y-%m-%d')
                                            except Exception:
                                                date_value = str(date.today())
                                            
                                            date_input = ui.input('Date *', value=date_value).props('type=date').classes('w-full')
                                            amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2, value=float(p.get('amount') or 0)).classes('w-full')
                                            method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                                                    label='Payment Method', value=p.get('payment_method') or '').classes('w-full')
                                            notes_input = ui.textarea('Notes', value=p.get('notes') or '').classes('w-full')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                                                
                                                def update_payment():
                                                    if not amount_input.value or amount_input.value <= 0:
                                                        ui.notify('Please enter a valid amount', type='warning')
                                                        return
                                                    
                                                    if db.update_payment(
                                                        payment_id=p['id'],
                                                        amount=amount_input.value,
                                                        payment_method=method_input.value or '',
                                                        notes=notes_input.value or '',
                                                        payment_date=date_input.value
                                                    ):
                                                        ui.notify('Sale updated successfully', type='positive')
                                                        edit_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to update sale', type='negative')
                                                
                                                ui.button('Update', on_click=update_payment)
                                        
                                        edit_dialog.open()
                                    return edit_handler
                                
                                def create_delete_handler_sales(p):
                                    def delete_handler():
                                        with ui.dialog() as delete_dialog, ui.card().classes('w-96'):
                                            ui.label('Delete Sale?').classes('text-xl font-bold mb-4')
                                            ui.label(f"Channel: {p.get('student_name') or 'Unknown'}").classes('text-gray-600')
                                            ui.label(f"Amount: {format_currency(float(p.get('amount') or 0))}").classes('text-gray-600 font-bold')
                                            ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
                                            
                                            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                                ui.button('Cancel', on_click=delete_dialog.close).props('flat')
                                                
                                                def confirm_delete():
                                                    if db.delete_payment(p['id']):
                                                        ui.notify('Sale deleted successfully', type='positive')
                                                        delete_dialog.close()
                                                        ui.navigate.to('/')
                                                    else:
                                                        ui.notify('Failed to delete sale', type='negative')
                                                
                                                ui.button('Delete', on_click=confirm_delete).props('color=red')
                                        
                                        delete_dialog.open()
                                    return delete_handler
                                
                                with ui.row().classes('gap-1'):
                                    ui.button('✏️', on_click=create_edit_handler_sales(payment)).props('flat dense color=blue').classes('text-sm')
                                    ui.button('🗑', on_click=create_delete_handler_sales(payment)).props('flat dense color=red').classes('text-sm')
                                ui.label('')  # Empty cell for layout
                    else:
                        ui.label('No sales recorded yet').classes('text-gray-500')
                        ui.label('Add sales channels (like "Market" or "Private Sale") as students with the sales channel flag.').classes('text-sm text-gray-400 mt-2')
