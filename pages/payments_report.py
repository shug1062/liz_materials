"""Payments report page"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from nicegui import ui

from database import Database
from utils import create_header, format_currency


db = Database()


def _parse_date_yyyy_mm_dd(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def payments_report_page():
    """View all payments with date filters and method summary."""
    create_header()

    with ui.column().classes('w-full items-center p-4'):
        with ui.row().classes('w-full max-w-6xl items-center justify-between mb-4'):
            ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label('Payments').classes('text-3xl font-bold')
            ui.button('Record Payment', on_click=lambda: ui.navigate.to('/payments')).props('outline')

        with ui.card().classes('w-full max-w-6xl mb-4'):
            ui.label('Filters').classes('text-lg font-bold mb-2')
            with ui.row().classes('w-full gap-4 items-end flex-wrap'):
                students = db.get_all_students()
                student_options = {'All Students': None}
                for s in students:
                    student_options[s['name']] = s['id']
                student_select = ui.select(
                    list(student_options.keys()),
                    label='Student',
                    value='All Students',
                ).classes('w-72')

                start_input = ui.input('Start Date').props('type=date').classes('w-56')
                end_input = ui.input('End Date').props('type=date').classes('w-56')

                def clear_filters():
                    student_select.value = 'All Students'
                    start_input.value = ''
                    end_input.value = ''
                    refresh()

                ui.button('Apply', on_click=lambda: refresh()).props('color=primary')
                ui.button('Clear', on_click=clear_filters).props('flat')

        summary_container = ui.row().classes('w-full max-w-6xl gap-4 mb-4')
        table_container = ui.column().classes('w-full max-w-6xl')

        def refresh():
            start_date = _parse_date_yyyy_mm_dd(start_input.value)
            end_date = _parse_date_yyyy_mm_dd(end_input.value)

            selected_student_id = student_options.get(student_select.value)

            payments = db.get_all_payments(
                start_date=start_date.isoformat() if start_date else None,
                end_date=end_date.isoformat() if end_date else None,
                student_id=selected_student_id,
            )

            total_amount = sum(float(p.get('amount') or 0) for p in payments)
            cash_total = sum(
                float(p.get('amount') or 0)
                for p in payments
                if (p.get('payment_method') or '').strip().lower() == 'cash'
            )
            card_total = sum(
                float(p.get('amount') or 0)
                for p in payments
                if (p.get('payment_method') or '').strip().lower() == 'card'
            )

            summary_container.clear()
            with summary_container:
                with ui.card().classes('flex-1 bg-green-50'):
                    ui.label('Total Payments').classes('text-sm text-gray-600')
                    ui.label(format_currency(total_amount)).classes('text-2xl font-bold text-green-700')
                with ui.card().classes('flex-1 bg-blue-50'):
                    ui.label('Cash').classes('text-sm text-gray-600')
                    ui.label(format_currency(cash_total)).classes('text-2xl font-bold text-blue-700')
                with ui.card().classes('flex-1 bg-purple-50'):
                    ui.label('Card').classes('text-sm text-gray-600')
                    ui.label(format_currency(card_total)).classes('text-2xl font-bold text-purple-700')

            table_container.clear()
            with table_container:
                if not payments:
                    ui.label('No payments found for the selected date range.').classes('text-gray-500')
                    return

                with ui.grid(columns=8).classes('w-full gap-2'):
                    ui.label('Date').classes('font-bold')
                    ui.label('Student').classes('font-bold')
                    ui.label('Class').classes('font-bold')
                    ui.label('Amount').classes('font-bold')
                    ui.label('Method').classes('font-bold')
                    ui.label('Notes').classes('font-bold')
                    ui.label('Actions').classes('font-bold')
                    ui.label('')  # Empty cell for layout

                    for p in payments:
                        raw_date = p.get('payment_date') or ''
                        try:
                            shown_date = datetime.fromisoformat(raw_date).strftime('%d/%m/%Y %H:%M')
                        except Exception:
                            try:
                                shown_date = datetime.fromisoformat(raw_date.split(' ')[0]).strftime('%d/%m/%Y')
                            except Exception:
                                shown_date = raw_date

                        ui.label(shown_date)
                        ui.label(p.get('student_name') or '')
                        ui.label(p.get('class_name') or '')
                        ui.label(format_currency(float(p.get('amount') or 0))).classes('font-bold text-green-700')
                        ui.label(p.get('payment_method') or '-')
                        ui.label(p.get('notes') or '-')
                        
                        # Action buttons
                        payment_id = p.get('id')
                        
                        def create_edit_handler(payment):
                            def edit_handler():
                                with ui.dialog() as edit_dialog, ui.card().classes('w-96'):
                                    ui.label('Edit Payment').classes('text-xl font-bold mb-4')
                                    
                                    # Parse the date for the input
                                    payment_date_str = payment.get('payment_date') or ''
                                    try:
                                        date_value = datetime.fromisoformat(payment_date_str.split(' ')[0]).strftime('%Y-%m-%d')
                                    except Exception:
                                        date_value = str(date.today())
                                    
                                    date_input = ui.input('Date *', value=date_value).props('type=date').classes('w-full')
                                    amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2, value=float(payment.get('amount') or 0)).classes('w-full')
                                    method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                                            label='Payment Method', value=payment.get('payment_method') or '').classes('w-full')
                                    notes_input = ui.textarea('Notes', value=payment.get('notes') or '').classes('w-full')
                                    
                                    with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                        ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                                        
                                        def update_payment():
                                            if not amount_input.value or amount_input.value <= 0:
                                                ui.notify('Please enter a valid amount', type='warning')
                                                return
                                            
                                            if db.update_payment(
                                                payment_id=payment['id'],
                                                amount=amount_input.value,
                                                payment_method=method_input.value or '',
                                                notes=notes_input.value or '',
                                                payment_date=date_input.value
                                            ):
                                                ui.notify('Payment updated successfully', type='positive')
                                                edit_dialog.close()
                                                refresh()
                                            else:
                                                ui.notify('Failed to update payment', type='negative')
                                        
                                        ui.button('Update', on_click=update_payment)
                                
                                edit_dialog.open()
                            return edit_handler
                        
                        def create_delete_handler(payment_data):
                            def delete_handler():
                                with ui.dialog() as delete_dialog, ui.card().classes('w-96'):
                                    ui.label('Delete Payment?').classes('text-xl font-bold mb-4')
                                    ui.label(f"Student: {payment_data.get('student_name') or 'Unknown'}").classes('text-gray-600')
                                    ui.label(f"Amount: {format_currency(float(payment_data.get('amount') or 0))}").classes('text-gray-600 font-bold')
                                    raw_date = payment_data.get('payment_date') or ''
                                    try:
                                        shown_date = datetime.fromisoformat(raw_date).strftime('%d/%m/%Y %H:%M')
                                    except Exception:
                                        try:
                                            shown_date = datetime.fromisoformat(raw_date.split(' ')[0]).strftime('%d/%m/%Y')
                                        except Exception:
                                            shown_date = raw_date
                                    ui.label(f"Date: {shown_date}").classes('text-gray-600')
                                    if payment_data.get('payment_method'):
                                        ui.label(f"Method: {payment_data['payment_method']}").classes('text-gray-600')
                                    ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
                                    
                                    with ui.row().classes('w-full justify-end gap-2 mt-4'):
                                        ui.button('Cancel', on_click=delete_dialog.close).props('flat')
                                        
                                        def confirm_delete():
                                            if db.delete_payment(payment_data['id']):
                                                ui.notify('Payment deleted successfully', type='positive')
                                                delete_dialog.close()
                                                refresh()
                                            else:
                                                ui.notify('Failed to delete payment', type='negative')
                                        
                                        ui.button('Delete', on_click=confirm_delete).props('color=red')
                                
                                delete_dialog.open()
                            return delete_handler
                        
                        with ui.row().classes('gap-1'):
                            ui.button('✏️', on_click=create_edit_handler(p)).props('flat dense color=blue').classes('text-sm')
                            ui.button('🗑', on_click=create_delete_handler(p)).props('flat dense color=red').classes('text-sm')

        refresh()
