"""Students management page"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency
from typing import Optional

db = Database()


def students_page(selected_class: Optional[str] = None):
    """Students management page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        with ui.row().classes('w-full max-w-6xl items-center justify-between mb-4'):
            ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label('Students').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                ui.button('⚙️ Reorder Classes', on_click=lambda: show_reorder_dialog()).props('flat color=blue-grey')
                ui.button('+ Add Student', on_click=lambda: show_add_student_dialog())
        
        # Student list with balances
        student_container = ui.column().classes('w-full max-w-6xl gap-4')
        
        def refresh_students():
            student_container.clear()
            balances = db.get_all_student_balances()
            
            # Group students by class
            classes = {}
            for balance in balances:
                student = db.get_student(balance['student_id'])
                class_name = student.get('class_name') or 'No Class Assigned'
                if class_name not in classes:
                    classes[class_name] = []
                classes[class_name].append({'student': student, 'balance': balance})
            
            with student_container:
                # Get custom class order
                ordered_classes = db.get_ordered_classes()
                
                # Add 'No Class Assigned' at the end if it exists
                if 'No Class Assigned' in classes and 'No Class Assigned' not in ordered_classes:
                    ordered_classes.append('No Class Assigned')
                
                # Display classes in custom order
                for class_name in ordered_classes:
                    students_in_class = classes[class_name]
                    
                    # Create an expansion panel for each class
                    # Set value=True to open, value=False to close
                    should_open = (selected_class is None) or (class_name == selected_class)
                    
                    with ui.expansion(class_name, icon='school', value=should_open).classes('w-full bg-blue-50 mb-2') as expansion:
                        
                        # Add class summary in header
                        total_owed = sum(s['balance']['balance'] for s in students_in_class if s['balance']['balance'] < 0)
                        total_credit = sum(s['balance']['balance'] for s in students_in_class if s['balance']['balance'] > 0)
                        
                        with expansion.add_slot('header'):
                            with ui.row().classes('w-full items-center justify-between'):
                                ui.label(class_name).classes('text-xl font-bold')
                                with ui.row().classes('gap-4'):
                                    ui.label(f"{len(students_in_class)} student{'s' if len(students_in_class) != 1 else ''}").classes('text-sm text-gray-600')
                                    if total_owed < 0:
                                        ui.label(f"Total Owed: {format_currency(abs(total_owed))}").classes('text-sm font-bold text-red-600')
                                    if total_credit > 0:
                                        ui.label(f"Total Credit: {format_currency(total_credit)}").classes('text-sm font-bold text-green-600')
                        
                        # Students in this class
                        for item in students_in_class:
                            student = item['student']
                            balance = item['balance']
                            
                            with ui.card().classes('w-full'):
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.column():
                                        ui.label(student['name']).classes('text-xl font-bold')
                                        if student['email']:
                                            ui.label(f"📧 {student['email']}").classes('text-sm text-gray-600')
                                        if student['phone']:
                                            ui.label(f"📱 {student['phone']}").classes('text-sm text-gray-600')
                                    
                                    with ui.column().classes('items-end'):
                                        balance_amount = balance['balance']
                                        if balance_amount < 0:
                                            ui.label(f"Owes: {format_currency(abs(balance_amount))}").classes('text-lg font-bold text-red-600')
                                        elif balance_amount > 0:
                                            ui.label(f"Credit: {format_currency(balance_amount)}").classes('text-lg font-bold text-green-600')
                                        else:
                                            ui.label('Settled').classes('text-lg font-bold text-gray-600')
                                        
                                        ui.label(f"Total Purchases: {format_currency(balance['total_purchases'])}").classes('text-sm text-gray-600')
                                        ui.label(f"Total Payments: {format_currency(balance['total_payments'])}").classes('text-sm text-gray-600')
                                    
                                    ui.button('View Details', on_click=lambda s_id=student['id']: ui.navigate.to(f'/student/{s_id}'))
        
        refresh_students()
        
        def show_reorder_dialog():
            """Show dialog to reorder classes"""
            # Get current ordered classes (excluding 'No Class Assigned')
            ordered_classes = db.get_ordered_classes()
            ordered_classes = [c for c in ordered_classes if c != 'No Class Assigned']
            
            # If no custom order exists yet, initialize it
            if not ordered_classes:
                # Get all unique class names from students
                all_students = db.get_all_students()
                unique_classes = sorted(list(set(s.get('class_name') for s in all_students if s.get('class_name') and s.get('class_name') != '')))
                db.set_class_order(unique_classes)
                ordered_classes = unique_classes
            
            class_list = ordered_classes.copy()
            
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Reorder Classes').classes('text-xl font-bold mb-4')
                ui.label('Use the arrows to change the order of classes').classes('text-sm text-gray-600 mb-4')
                
                list_container = ui.column().classes('w-full gap-2')
                
                def refresh_list():
                    list_container.clear()
                    with list_container:
                        for idx, class_name in enumerate(class_list):
                            with ui.row().classes('w-full items-center justify-between p-2 bg-gray-50 rounded'):
                                ui.label(class_name).classes('font-bold')
                                with ui.row().classes('gap-1'):
                                    # Up arrow
                                    up_btn = ui.button('↑', on_click=lambda i=idx: move_up(i)).props('flat dense size=sm')
                                    if idx == 0:
                                        up_btn.props('disable')
                                    
                                    # Down arrow
                                    down_btn = ui.button('↓', on_click=lambda i=idx: move_down(i)).props('flat dense size=sm')
                                    if idx == len(class_list) - 1:
                                        down_btn.props('disable')
                
                def move_up(idx):
                    if idx > 0:
                        class_list[idx], class_list[idx - 1] = class_list[idx - 1], class_list[idx]
                        refresh_list()
                
                def move_down(idx):
                    if idx < len(class_list) - 1:
                        class_list[idx], class_list[idx + 1] = class_list[idx + 1], class_list[idx]
                        refresh_list()
                
                refresh_list()
                
                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    
                    def save_order():
                        db.set_class_order(class_list)
                        ui.notify('Class order updated!', type='positive')
                        dialog.close()
                        refresh_students()
                    
                    ui.button('Save Order', on_click=save_order).props('color=primary')
            
            dialog.open()
        
        def show_add_student_dialog():
            # Get existing class names for autocomplete
            all_students = db.get_all_students()
            existing_classes = sorted(list(set(s.get('class_name') for s in all_students if s.get('class_name'))))
            
            # Ensure we always have a list (even if empty)
            class_options = existing_classes if existing_classes else []
            
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Add New Student').classes('text-xl font-bold mb-4')
                
                name_input = ui.input('Name *').classes('w-full')
                class_input = ui.input('Class Name', autocomplete=class_options).classes('w-full')
                ui.label('(Start typing to see suggestions)').classes('text-xs text-gray-500 -mt-2')
                email_input = ui.input('Email').classes('w-full')
                phone_input = ui.input('Phone').classes('w-full')
                notes_input = ui.textarea('Notes').classes('w-full')
                
                with ui.row().classes('w-full justify-end gap-2 mt-4'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    
                    def add_student():
                        if not name_input.value:
                            ui.notify('Please enter a name', type='warning')
                            return
                        
                        db.add_student(
                            name=name_input.value,
                            email=email_input.value or "",
                            phone=phone_input.value or "",
                            notes=notes_input.value or "",
                            class_name=class_input.value or ""
                        )
                        ui.notify(f'Student {name_input.value} added successfully!', type='positive')
                        dialog.close()
                        refresh_students()
                    
                    ui.button('Add Student', on_click=add_student)
            
            dialog.open()


def student_detail_page(student_id: int):
    """Individual student detail page"""
    create_header()
    
    student = db.get_student(student_id)
    if not student:
        ui.label('Student not found')
        return
    
    balance_info = db.get_student_balance(student_id)
    
    def show_edit_student_dialog(student_data):
        """Show dialog to edit student information"""
        # Get existing class names for autocomplete
        all_students = db.get_all_students()
        existing_classes = sorted(list(set(s.get('class_name') for s in all_students if s.get('class_name'))))
        
        # Ensure we always have a list (even if empty)
        class_options = existing_classes if existing_classes else []
        
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Edit Student Details').classes('text-xl font-bold mb-4')
            
            name_input = ui.input('Name *', value=student_data['name']).classes('w-full')
            class_input = ui.input('Class Name', value=student_data.get('class_name') or '', autocomplete=class_options).classes('w-full')
            ui.label('(Start typing to see suggestions)').classes('text-xs text-gray-500 -mt-2')
            email_input = ui.input('Email', value=student_data.get('email') or '').classes('w-full')
            phone_input = ui.input('Phone', value=student_data.get('phone') or '').classes('w-full')
            notes_input = ui.textarea('Notes', value=student_data.get('notes') or '').classes('w-full')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def update_student():
                    if not name_input.value:
                        ui.notify('Please enter a name', type='warning')
                        return
                    
                    db.update_student(
                        student_id=student_data['id'],
                        name=name_input.value,
                        email=email_input.value or "",
                        phone=phone_input.value or "",
                        notes=notes_input.value or "",
                        class_name=class_input.value or ""
                    )
                    ui.notify(f'Student {name_input.value} updated successfully!', type='positive')
                    dialog.close()
                    # Refresh the page to show updated information
                    ui.navigate.to(f'/student/{student_id}')
                
                ui.button('Update Student', on_click=update_student)
        
        dialog.open()
    
    def show_delete_student_dialog():
        """Show confirmation dialog to delete student"""
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('⚠️ Delete Student?').classes('text-xl font-bold mb-4 text-red-600')
            ui.label(f"Student: {student['name']}").classes('text-gray-800 font-bold')
            if student.get('class_name'):
                ui.label(f"Class: {student['class_name']}").classes('text-gray-600')
            
            ui.separator().classes('my-4')
            
            ui.label('This will permanently delete:').classes('font-bold text-red-600 mb-2')
            ui.label('• All purchase records').classes('text-sm text-gray-700')
            ui.label('• All payment records').classes('text-sm text-gray-700')
            ui.label('• All student information').classes('text-sm text-gray-700')
            
            ui.separator().classes('my-4')
            
            ui.label('⚠️ This action CANNOT be undone!').classes('text-red-600 font-bold')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def confirm_delete():
                    try:
                        db.delete_student(student_id)
                        ui.notify(f'Student {student["name"]} deleted successfully', type='positive')
                        dialog.close()
                        ui.navigate.to('/students')
                    except Exception as e:
                        ui.notify(f'Error deleting student: {str(e)}', type='negative')
                
                ui.button('Delete Permanently', on_click=confirm_delete).props('color=red')
        
        dialog.open()
    
    with ui.column().classes('w-full items-center p-4'):
        ui.button('← Back to Students', on_click=lambda: ui.navigate.to('/students')).props('flat').classes('self-start')
        
        # Student header
        with ui.card().classes('w-full max-w-6xl mb-4'):
            with ui.row().classes('w-full items-start justify-between'):
                with ui.column().classes('flex-grow'):
                    ui.label(student['name']).classes('text-3xl font-bold')
                    if student.get('class_name'):
                        ui.label(f"📚 Class: {student['class_name']}").classes('text-lg text-blue-600 font-semibold')
                    if student['email']:
                        ui.label(f"📧 {student['email']}")
                    if student['phone']:
                        ui.label(f"📱 {student['phone']}")
                    if student['notes']:
                        ui.label(f"Notes: {student['notes']}").classes('text-gray-600 mt-2')
                
                with ui.row().classes('gap-2'):
                    ui.button('✏️ Edit Details', on_click=lambda: show_edit_student_dialog(student)).props('outline')
                    ui.button('🗑️ Delete Student', on_click=show_delete_student_dialog).props('outline color=red')
        
        # Balance summary
        with ui.card().classes('w-full max-w-6xl mb-4 bg-gradient-to-r from-blue-50 to-purple-50'):
            ui.label('Balance Summary').classes('text-xl font-bold mb-4')
            with ui.row().classes('w-full gap-8'):
                with ui.column():
                    ui.label('Total Purchases').classes('text-sm text-gray-600')
                    ui.label(format_currency(balance_info['total_purchases'])).classes('text-2xl font-bold')
                
                with ui.column():
                    ui.label('Total Payments').classes('text-sm text-gray-600')
                    ui.label(format_currency(balance_info['total_payments'])).classes('text-2xl font-bold text-green-600')
                
                with ui.column():
                    ui.label('Balance').classes('text-sm text-gray-600')
                    balance = balance_info['balance']
                    color = 'text-red-600' if balance < 0 else 'text-green-600' if balance > 0 else 'text-gray-600'
                    status = f"Owes {format_currency(abs(balance))}" if balance < 0 else f"Credit {format_currency(balance)}" if balance > 0 else "Settled"
                    ui.label(status).classes(f'text-2xl font-bold {color}')
        
        # Tabs for purchases, payments, projects
        with ui.tabs().classes('w-full max-w-6xl') as tabs:
            purchases_tab = ui.tab('Purchases')
            payments_tab = ui.tab('Payments')
            projects_tab = ui.tab('Projects')
        
        with ui.tab_panels(tabs, value=purchases_tab).classes('w-full max-w-6xl'):
            # Purchases panel
            with ui.tab_panel(purchases_tab):
                purchases_container = ui.column().classes('w-full')
                
                def refresh_purchases():
                    purchases_container.clear()
                    purchases = db.get_student_purchases(student_id)
                    
                    with purchases_container:
                        if purchases:
                            with ui.grid(columns=7).classes('w-full gap-2'):
                                ui.label('Date').classes('font-bold')
                                ui.label('Material').classes('font-bold')
                                ui.label('Quantity').classes('font-bold')
                                ui.label('Unit Price').classes('font-bold')
                                ui.label('Total').classes('font-bold')
                                ui.label('Project').classes('font-bold')
                                ui.label('Actions').classes('font-bold')
                                
                                for purchase in purchases:
                                    date = datetime.fromisoformat(purchase['purchase_date']).strftime('%d/%m/%Y %H:%M')
                                    ui.label(date)
                                    ui.label(purchase['material_name'])
                                    ui.label(f"{purchase['quantity']:.2f} {purchase['unit_type']}")
                                    ui.label(format_currency(purchase['unit_price']))
                                    ui.label(format_currency(purchase['total_cost'])).classes('font-bold')
                                    ui.label(purchase['project_name'] or '-')
                                    
                                    with ui.row().classes('gap-1'):
                                        ui.button('✏️', on_click=lambda p=purchase: show_edit_purchase_dialog(p)).props('flat dense').tooltip('Edit purchase')
                                        ui.button('🗑️', on_click=lambda p=purchase: show_delete_purchase_dialog(p)).props('flat dense color=red').tooltip('Delete purchase')
                        else:
                            ui.label('No purchases yet').classes('text-gray-500')
                
                refresh_purchases()
            
            # Payments panel
            with ui.tab_panel(payments_tab):
                payments = db.get_student_payments(student_id)
                
                with ui.row().classes('w-full justify-end mb-4'):
                    ui.button('+ Record Payment', on_click=lambda: show_add_payment_dialog(student_id))
                
                if payments:
                    with ui.grid(columns=4).classes('w-full gap-2'):
                        ui.label('Date').classes('font-bold')
                        ui.label('Amount').classes('font-bold')
                        ui.label('Method').classes('font-bold')
                        ui.label('Notes').classes('font-bold')
                        
                        for payment in payments:
                            date = datetime.fromisoformat(payment['payment_date']).strftime('%d/%m/%Y %H:%M')
                            ui.label(date)
                            ui.label(format_currency(payment['amount'])).classes('font-bold text-green-600')
                            ui.label(payment['payment_method'] or '-')
                            ui.label(payment['notes'] or '-')
                else:
                    ui.label('No payments yet').classes('text-gray-500')
            
            # Projects panel
            with ui.tab_panel(projects_tab):
                projects = db.get_student_projects(student_id)
                
                with ui.row().classes('w-full justify-end mb-4'):
                    ui.button('+ Add Project', on_click=lambda: show_add_project_dialog(student_id))
                
                if projects:
                    for project in projects:
                        with ui.card().classes('w-full'):
                            ui.label(project['name']).classes('text-lg font-bold')
                            if project['description']:
                                ui.label(project['description']).classes('text-gray-600')
                            date = datetime.fromisoformat(project['created_at']).strftime('%d/%m/%Y')
                            ui.label(f"Started: {date}").classes('text-sm text-gray-500')
                else:
                    ui.label('No projects yet').classes('text-gray-500')
    
    def show_add_payment_dialog(student_id: int):
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Record Payment').classes('text-xl font-bold mb-4')
            
            amount_input = ui.number('Amount (£) *', min=0, step=0.01, precision=2).classes('w-full')
            method_input = ui.select(['Cash', 'Card', 'Bank Transfer', 'Other'], 
                                    label='Payment Method').classes('w-full')
            notes_input = ui.textarea('Notes').classes('w-full')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def add_payment():
                    if not amount_input.value or amount_input.value <= 0:
                        ui.notify('Please enter a valid amount', type='warning')
                        return
                    
                    db.add_payment(
                        student_id=student_id,
                        amount=amount_input.value,
                        payment_method=method_input.value or "",
                        notes=notes_input.value or ""
                    )
                    ui.notify(f'Payment of {format_currency(amount_input.value)} recorded!', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/student/{student_id}')  # Refresh page
                
                ui.button('Record Payment', on_click=add_payment)
        
        dialog.open()
    
    def show_add_project_dialog(student_id: int):
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Add New Project').classes('text-xl font-bold mb-4')
            
            name_input = ui.input('Project Name *').classes('w-full')
            desc_input = ui.textarea('Description').classes('w-full')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def add_project():
                    if not name_input.value:
                        ui.notify('Please enter a project name', type='warning')
                        return
                    
                    db.add_project(
                        name=name_input.value,
                        description=desc_input.value or ""
                    )
                    ui.notify(f'Project "{name_input.value}" added!', type='positive')
                    dialog.close()
                    ui.navigate.to(f'/student/{student_id}')  # Refresh page
                
                ui.button('Add Project', on_click=add_project)
        
        dialog.open()
    
    def show_edit_purchase_dialog(purchase):
        """Show dialog to edit an existing purchase"""
        # Get list of materials and projects
        materials = db.get_active_materials()
        all_projects = db.get_all_projects()
        
        material_options = {m['name']: m['id'] for m in materials}
        project_options = {p['name']: p['id'] for p in all_projects}
        
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Edit Purchase').classes('text-xl font-bold mb-4')
            
            # Pre-populate with existing values
            material_select = ui.select(
                list(material_options.keys()), 
                label='Material *',
                value=purchase['material_name']
            ).classes('w-full')
            
            quantity_input = ui.number(
                'Quantity *', 
                min=0.01, 
                step=0.01, 
                precision=2,
                value=purchase['quantity']
            ).classes('w-full')
            
            project_select = ui.select(
                ['None'] + list(project_options.keys()),
                label='Project (optional)',
                value=purchase['project_name'] if purchase['project_name'] else 'None'
            ).classes('w-full')
            
            # Parse existing date
            existing_date = datetime.fromisoformat(purchase['purchase_date'])
            date_input = ui.input(
                'Purchase Date',
                value=existing_date.strftime('%Y-%m-%d')
            ).classes('w-full')
            
            notes_input = ui.textarea(
                'Notes',
                value=purchase.get('notes', '') or ''
            ).classes('w-full')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def update_purchase():
                    if not material_select.value or not quantity_input.value:
                        ui.notify('Please fill in all required fields', type='warning')
                        return
                    
                    material_id = material_options[material_select.value]
                    project_id = project_options.get(project_select.value) if project_select.value != 'None' else None
                    
                    # Parse date and time
                    purchase_datetime = f"{date_input.value} {existing_date.strftime('%H:%M:%S')}"
                    
                    db.update_purchase(
                        purchase_id=purchase['id'],
                        student_id=student_id,
                        material_id=material_id,
                        quantity=quantity_input.value,
                        project_id=project_id,
                        notes=notes_input.value or "",
                        purchase_date=purchase_datetime
                    )
                    
                    ui.notify('Purchase updated successfully!', type='positive')
                    dialog.close()
                    refresh_purchases()
                
                ui.button('Update Purchase', on_click=update_purchase)
        
        dialog.open()
    
    def show_delete_purchase_dialog(purchase):
        """Show confirmation dialog to delete a purchase"""
        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Delete Purchase?').classes('text-xl font-bold mb-4')
            ui.label(f"Material: {purchase['material_name']}").classes('text-gray-600')
            ui.label(f"Quantity: {purchase['quantity']:.2f} {purchase['unit_type']}").classes('text-gray-600')
            ui.label(f"Total: {format_currency(purchase['total_cost'])}").classes('text-gray-600 font-bold')
            ui.label('This action cannot be undone.').classes('text-red-600 mt-4')
            
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                
                def delete_purchase():
                    db.delete_purchase(purchase['id'])
                    ui.notify('Purchase deleted successfully!', type='positive')
                    dialog.close()
                    refresh_purchases()
                
                ui.button('Delete', on_click=delete_purchase).props('color=red')
        
        dialog.open()
