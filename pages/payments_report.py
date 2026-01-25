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

                with ui.grid(columns=6).classes('w-full gap-2'):
                    ui.label('Date').classes('font-bold')
                    ui.label('Student').classes('font-bold')
                    ui.label('Class').classes('font-bold')
                    ui.label('Amount').classes('font-bold')
                    ui.label('Method').classes('font-bold')
                    ui.label('Notes').classes('font-bold')

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

        refresh()
