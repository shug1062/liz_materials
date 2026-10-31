"""Payment recording page"""
from nicegui import ui
from database import Database
from utils import create_header, format_currency
from datetime import date
from typing import Optional
from urllib.parse import quote

db = Database()


def payments_page(
    selected_class: Optional[str] = None,
    selected_student_id: Optional[int] = None,
    return_to: Optional[str] = None,
):
    """Record payment page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        with ui.row().classes('w-full max-w-2xl items-center gap-2'):
            # When both are available, show both options.
            if selected_student_id is not None:
                ui.button(
                    '← Back to Student',
                    on_click=lambda s_id=selected_student_id: ui.navigate.to(f'/student/{s_id}')
                ).props('flat')

            if selected_class:
                encoded_class = quote(selected_class)
                ui.button(
                    '← Back to Students',
                    on_click=lambda cn=encoded_class: ui.navigate.to(f'/students?class_name={cn}')
                ).props('flat')
            
            # Always show Back to Dashboard
            ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')

        if selected_class:
            ui.label(f'Class: {selected_class}').classes('w-full max-w-2xl text-sm text-gray-600')
        
        with ui.card().classes('w-full max-w-2xl'):
            ui.label('Record Payment').classes('text-2xl font-bold mb-4')
            
            students = db.get_all_students()

            if selected_class:
                students = [s for s in students if (s.get('class_name') or 'No Class Assigned') == selected_class]
            
            if not students:
                if selected_class:
                    ui.label('No students found in this class').classes('text-red-600')
                else:
                    ui.label('Please add students first').classes('text-red-600')
                return
            
            student_options = {s['name']: s['id'] for s in students}
            student_select = ui.select(list(student_options.keys()), label='Student *').classes('w-full')
            
            # Show current balance
            balance_label = ui.label('').classes('text-lg font-bold')
            
            def update_balance():
                if student_select.value:
                    student_id = student_options[student_select.value]
                    balance_info = db.get_student_balance(student_id)
                    balance = balance_info['balance']
                    
                    if balance < 0:
                        balance_label.text = f"Current Balance: Owes {format_currency(abs(balance))}"
                        balance_label.classes('text-lg font-bold text-red-600')
                    elif balance > 0:
                        balance_label.text = f"Current Balance: Credit {format_currency(balance)}"
                        balance_label.classes('text-lg font-bold text-green-600')
                    else:
                        balance_label.text = "Current Balance: Settled"
                        balance_label.classes('text-lg font-bold text-gray-600')
            
            student_select.on('update:model-value', update_balance)

            if selected_student_id is not None:
                preselected_name = next(
                    (name for name, s_id in student_options.items() if s_id == selected_student_id),
                    None,
                )
                if preselected_name:
                    student_select.value = preselected_name
                    update_balance()
            
            # Date input (defaults to today)
            date_input = ui.input('Date *', value=str(date.today())).props('type=date').classes('w-full')
            
            amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2).classes('w-full')
            method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                    label='Payment Method').classes('w-full')
            notes_input = ui.textarea('Notes').classes('w-full')
            
            def record_payment():
                if not student_select.value or not amount_input.value or amount_input.value <= 0 or not date_input.value:
                    ui.notify('Please fill in all required fields', type='warning')
                    return
                
                student_id = student_options[student_select.value]
                
                db.add_payment(
                    student_id=student_id,
                    amount=amount_input.value,
                    payment_method=method_input.value or "",
                    notes=notes_input.value or "",
                    payment_date=date_input.value
                )
                
                ui.notify(f'Payment of {format_currency(amount_input.value)} recorded!', type='positive')
                if return_to == 'student' and selected_student_id is not None:
                    ui.navigate.to(f'/student/{selected_student_id}')
                elif selected_class:
                    encoded_class = quote(selected_class)
                    ui.navigate.to(f'/students?class_name={encoded_class}')
                else:
                    ui.navigate.to(f'/student/{student_id}')
            
            ui.button('Record Payment', on_click=record_payment).classes('w-full mt-4')
