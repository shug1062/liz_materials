"""Purchase recording page"""
from nicegui import ui
from database import Database
from utils import create_header, format_currency
from datetime import date
from typing import Optional
from urllib.parse import quote

db = Database()


def purchases_page(
    selected_class: Optional[str] = None,
    selected_student_id: Optional[int] = None,
    return_to: Optional[str] = None,
):
    """Record new purchase page"""
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

            if selected_student_id is None and not selected_class:
                ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')

        if selected_class:
            ui.label(f'Class: {selected_class}').classes('w-full max-w-2xl text-sm text-gray-600')
        
        with ui.card().classes('w-full max-w-2xl'):
            ui.label('Record New Purchase').classes('text-2xl font-bold mb-4')
            
            students = db.get_all_students()
            materials = db.get_active_materials()  # Only show active materials

            if selected_class:
                students = [s for s in students if (s.get('class_name') or 'No Class Assigned') == selected_class]
            
            if not students:
                if selected_class:
                    ui.label('No students found in this class').classes('text-red-600')
                else:
                    ui.label('Please add students first').classes('text-red-600')
                return
            
            if not materials:
                ui.label('No active materials available. Please add materials first.').classes('text-red-600')
                return
            
            student_options = {s['name']: s['id'] for s in students}
            student_select = ui.select(list(student_options.keys()), label='Student *').classes('w-full')

            if selected_student_id is not None:
                # Preselect student if present in the options
                preselected_name = next(
                    (name for name, s_id in student_options.items() if s_id == selected_student_id),
                    None,
                )
                if preselected_name:
                    student_select.value = preselected_name
            
            # Project selection - show all projects since they're now independent
            all_projects = db.get_all_projects()
            project_options = {p['name']: p['id'] for p in all_projects}
            project_select = ui.select(['None'] + list(project_options.keys()), 
                                       label='Project (optional)',
                                       value='None').classes('w-full')
            
            # Date input (defaults to today)
            date_input = ui.input('Date *', value=str(date.today())).props('type=date').classes('w-full')
            
            material_options = {f"{m['name']} ({m['category']})": m['id'] for m in materials}
            material_select = ui.select(list(material_options.keys()), label='Material *').classes('w-full')
            
            quantity_input = ui.number('Quantity *', min=0, step=0.01, precision=2).classes('w-full')
            
            # Show unit type and price
            unit_label = ui.label('').classes('text-sm text-gray-600')
            price_label = ui.label('').classes('text-lg font-bold')
            total_label = ui.label('').classes('text-2xl font-bold text-green-600')
            
            def update_price_info():
                if material_select.value and quantity_input.value:
                    material_id = material_options[material_select.value]
                    material = db.get_material(material_id)
                    
                    # Calculate prices with pack quantity consideration and pricing type
                    pricing_type = material.get('pricing_type', 'fixed')
                    base_price = material['base_price']
                    pack_qty = material.get('pack_quantity', 1)
                    markup = material.get('markup_percentage', 0)
                    
                    # Calculate per-item prices based on pricing type
                    if pricing_type == 'per_kg_item' and material.get('weight_per_unit'):
                        # Item weight-based: price_per_gram * grams_per_item
                        price_per_item = base_price * material['weight_per_unit']
                    else:
                        # Fixed or bulk per_kg: divide pack price by quantity
                        price_per_item = base_price / pack_qty if pack_qty > 0 else base_price
                    
                    final_price_per_item = price_per_item * (1 + markup / 100)
                    
                    unit_label.text = f"Unit: {material['unit_type']}"
                    
                    # Show pack information if applicable (without markup details)
                    if pricing_type == 'per_kg_item':
                        # Show weight-based pricing info
                        weight = material.get('weight_per_unit', 0)
                        price_label.text = (
                            f"{format_currency(base_price)}/g × {weight}g = "
                            f"{format_currency(price_per_item)}/item | "
                            f"Price: {format_currency(final_price_per_item)} per {material['unit_type']}"
                        )
                    elif pack_qty > 1:
                        price_label.text = (
                            f"Pack of {int(pack_qty)} @ {format_currency(base_price)} = "
                            f"{format_currency(price_per_item)}/item | "
                            f"Price: {format_currency(final_price_per_item)} per {material['unit_type']}"
                        )
                    else:
                        price_label.text = (
                            f"Price: {format_currency(final_price_per_item)} per {material['unit_type']}"
                        )
                    
                    total = final_price_per_item * quantity_input.value
                    total_label.text = f"Total Cost: {format_currency(total)}"
            
            material_select.on('update:model-value', update_price_info)
            quantity_input.on('update:model-value', update_price_info)
            
            notes_input = ui.textarea('Notes').classes('w-full')
            
            def record_purchase():
                if not student_select.value or not material_select.value or not quantity_input.value or not date_input.value:
                    ui.notify('Please fill in all required fields', type='warning')
                    return
                
                student_id = student_options[student_select.value]
                material_id = material_options[material_select.value]
                
                # Get project ID if selected
                project_id = None
                if project_select.value and project_select.value != 'None':
                    project_id = project_options.get(project_select.value)
                
                db.add_purchase(
                    student_id=student_id,
                    material_id=material_id,
                    quantity=quantity_input.value,
                    project_id=project_id,
                    notes=notes_input.value or "",
                    purchase_date=date_input.value
                )
                
                ui.notify('Purchase recorded successfully!', type='positive')
                if return_to == 'student' and selected_student_id is not None:
                    ui.navigate.to(f'/student/{selected_student_id}')
                elif selected_class:
                    encoded_class = quote(selected_class)
                    ui.navigate.to(f'/students?class_name={encoded_class}')
                else:
                    ui.navigate.to(f'/student/{student_id}')
            
            ui.button('Record Purchase', on_click=record_purchase).classes('w-full mt-4')
