"""Payment recording page"""
from nicegui import ui
from database import Database
from utils import create_header, format_currency
from datetime import date

db = Database()


def payments_page():
    """Record payment page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat').classes('self-start')
        
        with ui.card().classes('w-full max-w-2xl'):
            ui.label('Record Payment').classes('text-2xl font-bold mb-4')
            
            students = db.get_all_students()
            
            if not students:
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
                ui.navigate.to(f'/student/{student_id}')
            
            ui.button('Record Payment', on_click=record_payment).classes('w-full mt-4')
