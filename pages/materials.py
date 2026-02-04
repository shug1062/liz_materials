"""Materials management page - REFACTORED for better maintainability"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency
from price_scraper import get_material_price_from_url, scrape_weight_per_unit
from ui_helpers import create_price_calculator

db = Database()


def normalize_category(category_input: str, existing_categories: list) -> str:
    """
    Normalize category name to match existing category (case-insensitive).
    If a matching category exists, return it. Otherwise return the input as-is.
    """
    if not category_input:
        return ""
    
    # Strip whitespace
    category_input = category_input.strip()
    
    # Check if there's an existing category that matches case-insensitively
    for existing in existing_categories:
        if existing.lower() == category_input.lower():
            return existing  # Return the existing category with its original case
    
    # No match found, return the input (will create new category)
    return category_input


# ============ ACTION FUNCTIONS (Extracted from nested scope) ============

def toggle_material_status(material, refresh_callback):
    """Toggle material active/inactive status"""
    current_status = material.get('is_active', 1)
    db.toggle_material_active(material['id'])
    status_text = "inactive" if current_status else "active"
    ui.notify(f"Material marked as {status_text}!", type='positive')
    refresh_callback()


def update_all_prices(refresh_callback):
    """Update prices for all materials with supplier URLs"""
    materials = db.get_all_materials()
    materials_with_urls = [m for m in materials if m.get('supplier_url')]
    
    if not materials_with_urls:
        ui.notify('No materials have supplier URLs to update', type='warning')
        return
    
    ui.notify(f'Updating prices for {len(materials_with_urls)} materials...', type='info')
    
    updated = 0
    failed = 0
    
    for material in materials_with_urls:
        pricing_type = material.get('pricing_type', 'fixed')
        new_price = get_material_price_from_url(
            material['supplier_url'], 
            use_vat=True,
            pricing_type=pricing_type
        )
        
        if new_price:
            db.update_material_price(material['id'], new_price)
            updated += 1
        else:
            failed += 1
    
    ui.notify(f'Updated {updated} prices. {failed} failed.', type='positive' if failed == 0 else 'warning')
    refresh_callback()


def delete_material(material, refresh_callback):
    """Delete a material with confirmation dialog"""
    with ui.dialog() as dialog, ui.card():
        ui.label(f'Delete material "{material["name"]}"?').classes('text-lg')
        ui.label('⚠️ This cannot be undone.').classes('text-sm text-orange-600 mb-4')
        
        with ui.row().classes('gap-2'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            
            def confirm_delete():
                db.delete_material(material['id'])
                ui.notify(f'Material "{material["name"]}" deleted', type='positive')
                dialog.close()
                refresh_callback()
            
            ui.button('Delete', on_click=confirm_delete).props('color=red')
    
    dialog.open()


def update_price_from_url(material, refresh_callback):
    """Update material price by scraping from supplier URL"""
    if not material.get('supplier_url'):
        ui.notify('No supplier URL available', type='warning')
        return
    
    ui.notify('Fetching price from supplier...', type='info')
    
    # Get pricing type (default to 'fixed' for existing materials)
    pricing_type = material.get('pricing_type', 'fixed')
    
    # Scrape the price
    new_price = get_material_price_from_url(
        material['supplier_url'], 
        use_vat=True,
        pricing_type=pricing_type
    )
    
    # If it's item weight-based pricing, also try to scrape weight per unit
    weight_per_unit = None
    if pricing_type == 'per_kg_item':
        weight_per_unit = scrape_weight_per_unit(material['supplier_url'])
    
    if new_price:
        # Update the base price in database
        old_price = material['base_price']
        markup = material.get('markup_percentage', 0)
        
        # Update the material with new price and potentially weight
        db.update_material(
            material_id=material['id'],
            name=material['name'],
            category=material['category'],
            unit_type=material['unit_type'],
            base_price=new_price,
            pack_quantity=material.get('pack_quantity', 1),
            markup_percentage=markup,
            supplier=material['supplier'],
            supplier_url=material['supplier_url'],
            notes=material.get('notes', ''),
            is_active=bool(material.get('is_active', 1)),
            pricing_type=pricing_type,
            weight_per_unit=weight_per_unit if weight_per_unit else material.get('weight_per_unit')
        )
        
        price_label = 'per g' if pricing_type == 'per_kg' else ''
        weight_msg = f' | Weight: {weight_per_unit}g/unit' if weight_per_unit else ''
        ui.notify(
            f'✅ Price updated! {format_currency(old_price)} → {format_currency(new_price)} {price_label}{weight_msg}',
            type='positive'
        )
        refresh_callback()
    else:
        ui.notify('❌ Failed to fetch price from supplier', type='negative')


# ============ DIALOG FUNCTIONS (Extracted from nested scope) ============

def show_add_material_dialog(refresh_callback):
    """Show dialog to add a new material"""
    # Get existing categories from database
    all_materials = db.get_all_materials()
    existing_categories = sorted(list(set(m['category'] for m in all_materials if m.get('category'))))
    
    # Ensure we always have some default categories
    default_categories = ['Sheet Silver', 'Wire', 'Gemstones', 'Findings', 'Tools', 'Other']
    all_categories = existing_categories if existing_categories else default_categories
    
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Add New Material').classes('text-xl font-bold mb-4')
        
        name_input = ui.input('Material Name *').classes('w-full')
        
        # Use regular input with autocomplete for better reliability
        category_input = ui.input('Category', autocomplete=all_categories).classes('w-full')
        ui.label('(Type or select from suggestions)').classes('text-xs text-gray-500 -mt-2')
        
        unit_input = ui.select(['gram', 'item', 'cm', 'mm', 'sheet', 'piece'], 
                              label='Unit Type').classes('w-full')
        
        ui.separator()
        ui.label('Pricing Information').classes('text-sm font-bold text-gray-700 mt-2')
        
        pricing_type_select = ui.select(
            ['Fixed Price', 'Per Gram (g)', 'Per Gram (item weight)'],
            label='Pricing Type',
            value='Fixed Price'
        ).classes('w-full')
        ui.label('(Fixed: Standard pricing | Per g: Bulk weight | Per g (item weight): Items sold by weight)').classes('text-xs text-gray-500 -mt-2')
        
        price_input = ui.number('Pack/Supplier Price (£) *', min=0, step=0.01, precision=2).classes('w-full')
        pack_qty_input = ui.number('Items in Pack', min=1, step=1, precision=0, value=1).classes('w-full')
        ui.label('(Enter 1 if sold individually, or the pack size like 50)').classes('text-xs text-gray-500 -mt-2')
        
        # Weight per unit field (only for Per Gram pricing)
        weight_container = ui.column().classes('w-full')
        weight_input = None
        
        # Forward declaration of update function (will be defined later)
        update_price_calculations_func = None
        
        def update_weight_visibility():
            weight_container.clear()
            nonlocal weight_input
            if pricing_type_select.value == 'Per Gram (item weight)':
                with weight_container:
                    ui.label('Item Weight Information').classes('text-sm font-bold text-gray-700 mt-2')
                    ui.label('For items sold by weight but used individually (e.g., jump rings)').classes('text-xs text-gray-500')
                    weight_input = ui.number('Weight per Item (grams)', min=0, step=0.001, precision=4).classes('w-full')
                    ui.label('(Weight of one individual item)').classes('text-xs text-gray-500 -mt-2')
                    
                    # Attach price calculator callback
                    if update_price_calculations_func:
                        weight_input.on('update:model-value', update_price_calculations_func)
                    
                    def fetch_weight():
                        if not url_input.value:
                            ui.notify('Please enter Supplier URL first', type='warning')
                            return
                        ui.notify('Fetching weight info...', type='info')
                        weight = scrape_weight_per_unit(url_input.value)
                        if weight:
                            weight_input.value = weight
                            if update_price_calculations_func:
                                update_price_calculations_func()
                            ui.notify(f'✅ Weight found: {weight}g per unit', type='positive')
                        else:
                            ui.notify('⚠️ Could not find weight info on page', type='warning')
                    
                    ui.button('🔍 Auto-fetch Weight from URL', on_click=fetch_weight).classes('w-full').props('color=purple flat')
            else:
                weight_input = None
                if update_price_calculations_func:
                    update_price_calculations_func()
        
        pricing_type_select.on('update:model-value', lambda: update_weight_visibility())
        update_weight_visibility()  # Initial setup
        
        markup_input = ui.number('Markup Percentage (%)', min=0, max=1000, step=0.1, precision=1, value=0).classes('w-full')
        
        # Show price calculations
        ui.separator()
        price_per_item_label = ui.label('Price per item: £0.00').classes('text-sm text-gray-600')
        final_price_label = ui.label('Final Price per item: £0.00').classes('text-lg font-bold text-green-600')
        
        # Custom price calculator that handles weight-based pricing
        def update_price_calculations():
            if price_input.value and pack_qty_input.value and markup_input.value is not None:
                pack_price = price_input.value
                pack_qty = pack_qty_input.value if pack_qty_input.value > 0 else 1
                
                # Check if weight-based pricing
                pricing_type_value = pricing_type_select.value
                
                if pricing_type_value == 'Per Gram (item weight)' and weight_input and weight_input.value:
                    # Weight-based: price_per_gram * grams_per_item
                    price_per_item = pack_price * weight_input.value
                else:
                    # Fixed: divide pack price by quantity
                    price_per_item = pack_price / pack_qty
                
                # Apply markup
                final_per_item = price_per_item * (1 + markup_input.value / 100)
                
                # Update labels
                price_per_item_label.text = f'Cost per item: {format_currency(price_per_item)}'
                final_price_label.text = f'Final Price per item: {format_currency(final_per_item)}'
        
        # Make the function available to update_weight_visibility
        update_price_calculations_func = update_price_calculations
        
        price_input.on('update:model-value', update_price_calculations)
        pack_qty_input.on('update:model-value', update_price_calculations)
        markup_input.on('update:model-value', update_price_calculations)
        pricing_type_select.on('update:model-value', update_price_calculations)
        
        ui.separator()
        supplier_input = ui.input('Supplier', value='Cooksongold').classes('w-full')
        url_input = ui.input('Supplier URL').classes('w-full')
        notes_input = ui.textarea('Notes').classes('w-full')
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            
            def add_material():
                if not name_input.value or not price_input.value or not unit_input.value:
                    ui.notify('Please fill in required fields', type='warning')
                    return
                
                pack_qty = pack_qty_input.value if pack_qty_input.value and pack_qty_input.value > 0 else 1
                
                # Map UI pricing type to database pricing type
                if pricing_type_select.value == 'Per Gram (g)':
                    pricing_type = 'per_kg'
                elif pricing_type_select.value == 'Per Gram (item weight)':
                    pricing_type = 'per_kg_item'
                else:
                    pricing_type = 'fixed'
                
                # Get category and normalize it to match existing categories (case-insensitive)
                category_value = normalize_category(category_input.value or "", all_categories)
                
                db.add_material(
                    name=name_input.value,
                    category=category_value,
                    unit_type=unit_input.value,
                    base_price=price_input.value,
                    pack_quantity=pack_qty,
                    markup_percentage=markup_input.value or 0,
                    supplier=supplier_input.value or "Cooksongold",
                    supplier_url=url_input.value or "",
                    notes=notes_input.value or "",
                    pricing_type=pricing_type,
                    weight_per_unit=weight_input.value if weight_input and weight_input.value else None
                )
                ui.notify(f'Material {name_input.value} added!', type='positive')
                dialog.close()
                refresh_callback()
            
            ui.button('Add Material', on_click=add_material)
    
    dialog.open()


def show_edit_material_dialog(material, refresh_callback):
    """Show dialog to edit an existing material"""
    # Get existing categories from database
    all_materials = db.get_all_materials()
    existing_categories = sorted(list(set(m['category'] for m in all_materials if m.get('category'))))
    
    # Ensure current category is in the list
    if material.get('category') and material['category'] not in existing_categories:
        existing_categories.insert(0, material['category'])
    
    # Ensure we always have some default categories
    if not existing_categories:
        existing_categories = ['Sheet Silver', 'Wire', 'Gemstones', 'Findings', 'Tools', 'Other']
    
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Edit Material').classes('text-xl font-bold mb-4')
        
        name_input = ui.input('Material Name *', value=material['name']).classes('w-full')
        
        # Use regular input with autocomplete instead of select for better reliability
        current_category = material.get('category') or ""
        category_input = ui.input('Category', value=current_category, autocomplete=existing_categories).classes('w-full')
        ui.label('(Type or select from suggestions)').classes('text-xs text-gray-500 -mt-2')
        unit_input = ui.select(['gram', 'item', 'cm', 'mm', 'sheet', 'piece'], 
                              label='Unit Type',
                              value=material['unit_type']).classes('w-full')
        
        ui.separator()
        ui.label('Pricing Information').classes('text-sm font-bold text-gray-700 mt-2')
        
        current_pricing_type = material.get('pricing_type', 'fixed')
        
        # Map database pricing type to UI label
        if current_pricing_type == 'per_kg':
            current_value = 'Per Gram (g)'
        elif current_pricing_type == 'per_kg_item':
            current_value = 'Per Gram (item weight)'
        else:
            current_value = 'Fixed Price'
        
        pricing_type_select = ui.select(
            ['Fixed Price', 'Per Gram (g)', 'Per Gram (item weight)'],
            label='Pricing Type',
            value=current_value
        ).classes('w-full')
        
        price_input = ui.number('Pack/Supplier Price (£) *', min=0, step=0.01, precision=2, 
                               value=material['base_price']).classes('w-full')
        pack_qty_input = ui.number('Items in Pack', min=1, step=1, precision=0,
                                  value=material.get('pack_quantity', 1)).classes('w-full')
        
        # Weight per unit field (only shown for per_kg pricing)
        weight_container = ui.column().classes('w-full')
        weight_input = None
        
        # Forward declaration of update function (will be defined later)
        update_price_calculations_func = None
        
        def update_weight_visibility():
            nonlocal weight_input
            weight_container.clear()
            with weight_container:
                if pricing_type_select.value == 'Per Gram (item weight)':
                    weight_input = ui.number('Weight per Item (grams)', min=0, step=0.001, precision=4,
                                            value=material.get('weight_per_unit')).classes('w-full')
                    ui.label('(Weight of one individual item)').classes('text-xs text-gray-500 -mt-2')
                    
                    # Attach price calculator callback
                    if update_price_calculations_func:
                        weight_input.on('update:model-value', update_price_calculations_func)
                    
                    def fetch_weight():
                        if not url_input.value:
                            ui.notify('Please enter a supplier URL first', type='warning')
                            return
                        try:
                            weight = scrape_weight_per_unit(url_input.value)
                            if weight:
                                weight_input.value = weight
                                if update_price_calculations_func:
                                    update_price_calculations_func()
                                ui.notify(f'Weight fetched: {weight:.4f}g per item', type='positive')
                            else:
                                ui.notify('Could not find weight information on page', type='warning')
                        except Exception as e:
                            ui.notify(f'Error fetching weight: {str(e)}', type='negative')
                    
                    ui.button('🔍 Auto-fetch Weight from URL', on_click=fetch_weight).props('flat color=purple')
                else:
                    weight_input = None
                    if update_price_calculations_func:
                        update_price_calculations_func()
        
        update_weight_visibility()
        pricing_type_select.on('update:model-value', lambda: update_weight_visibility())
        
        markup_input = ui.number('Markup Percentage (%)', min=0, max=1000, step=0.1, precision=1,
                                value=material.get('markup_percentage', 0)).classes('w-full')
        
        # Show price calculations
        ui.separator()
        pack_qty = material.get('pack_quantity', 1)
        
        # Calculate initial price per item based on pricing type
        pricing_type = material.get('pricing_type', 'fixed')
        if pricing_type == 'per_kg_item' and material.get('weight_per_unit'):
            price_per_item = material['base_price'] * material['weight_per_unit']
        else:
            price_per_item = material['base_price'] / pack_qty if pack_qty > 0 else material['base_price']
        
        final_per_item = price_per_item * (1 + material.get('markup_percentage', 0) / 100)
        
        price_per_item_label = ui.label(f'Cost per item: {format_currency(price_per_item)}').classes('text-sm text-gray-600')
        final_price_label = ui.label(f'Final Price per item: {format_currency(final_per_item)}').classes('text-lg font-bold text-green-600')
        
        # Custom price calculator that handles weight-based pricing
        def update_price_calculations():
            if price_input.value and pack_qty_input.value and markup_input.value is not None:
                pack_price = price_input.value
                pack_qty = pack_qty_input.value if pack_qty_input.value > 0 else 1
                
                # Check if weight-based pricing
                pricing_type_value = pricing_type_select.value
                
                if pricing_type_value == 'Per Gram (item weight)' and weight_input and weight_input.value:
                    # Weight-based: price_per_gram * grams_per_item
                    price_per_item = pack_price * weight_input.value
                else:
                    # Fixed: divide pack price by quantity
                    price_per_item = pack_price / pack_qty
                
                # Apply markup
                final_per_item = price_per_item * (1 + markup_input.value / 100)
                
                # Update labels
                price_per_item_label.text = f'Cost per item: {format_currency(price_per_item)}'
                final_price_label.text = f'Final Price per item: {format_currency(final_per_item)}'
        
        # Make the function available to update_weight_visibility
        update_price_calculations_func = update_price_calculations
        
        price_input.on('update:model-value', update_price_calculations)
        pack_qty_input.on('update:model-value', update_price_calculations)
        markup_input.on('update:model-value', update_price_calculations)
        pricing_type_select.on('update:model-value', update_price_calculations)
        
        ui.separator()
        supplier_input = ui.input('Supplier', value=material['supplier']).classes('w-full')
        url_input = ui.input('Supplier URL', value=material['supplier_url'] or "").classes('w-full')
        notes_input = ui.textarea('Notes', value=material['notes'] or "").classes('w-full')
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            
            def update_material():
                if not name_input.value or not price_input.value:
                    ui.notify('Please fill in required fields', type='warning')
                    return
                
                pack_qty = pack_qty_input.value if pack_qty_input.value and pack_qty_input.value > 0 else 1
                
                # Map UI pricing type to database pricing type
                if pricing_type_select.value == 'Per Gram (g)':
                    pricing_type = 'per_kg'
                elif pricing_type_select.value == 'Per Gram (item weight)':
                    pricing_type = 'per_kg_item'
                else:
                    pricing_type = 'fixed'
                
                # Get category and normalize it to match existing categories (case-insensitive)
                category_value = normalize_category(category_input.value or "", existing_categories)
                
                db.update_material(
                    material_id=material['id'],
                    name=name_input.value,
                    category=category_value,
                    unit_type=unit_input.value,
                    base_price=price_input.value,
                    pack_quantity=pack_qty,
                    markup_percentage=markup_input.value or 0,
                    supplier=supplier_input.value,
                    supplier_url=url_input.value or "",
                    notes=notes_input.value or "",
                    pricing_type=pricing_type,
                    weight_per_unit=weight_input.value if weight_input and weight_input.value else None
                )
                ui.notify(f'Material {name_input.value} updated! Category: {category_value}', type='positive')
                dialog.close()
                refresh_callback()
            
            ui.button('Update Material', on_click=update_material)
    
    dialog.open()


# ============ TABLE RENDERING (Extracted for clarity) ============

def show_reorder_categories_dialog(refresh_callback):
    """Show dialog to reorder material categories"""
    ordered_categories = db.get_ordered_categories()
    
    if not ordered_categories:
        ui.notify('No categories found', type='warning')
        return
    
    # Initialize the category order in the database if not already set
    # This ensures all categories are in the category_order table
    db.set_category_order(ordered_categories)
    
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Reorder Categories').classes('text-xl font-bold mb-4')
        ui.label('Use arrows to change the order of categories').classes('text-sm text-gray-600 mb-4')
        
        # Container for the category list
        list_container = ui.column().classes('w-full gap-2')
        
        def render_list():
            list_container.clear()
            current_order = db.get_ordered_categories()
            
            with list_container:
                for idx, category in enumerate(current_order):
                    with ui.row().classes('w-full items-center gap-2 p-2 bg-gray-50 rounded'):
                        ui.label(category).classes('flex-grow')
                        
                        with ui.row().classes('gap-1'):
                            # Up arrow
                            if idx > 0:
                                def move_up(cat=category):
                                    result = db.move_category_up(cat)
                                    if result:
                                        render_list()
                                    else:
                                        ui.notify('Could not move category up', type='warning')
                                ui.button('↑', on_click=move_up).props('dense flat size=sm')
                            else:
                                ui.label('').classes('w-8')  # Spacer
                            
                            # Down arrow
                            if idx < len(current_order) - 1:
                                def move_down(cat=category):
                                    result = db.move_category_down(cat)
                                    if result:
                                        render_list()
                                    else:
                                        ui.notify('Could not move category down', type='warning')
                                ui.button('↓', on_click=move_down).props('dense flat size=sm')
                            else:
                                ui.label('').classes('w-8')  # Spacer
        
        render_list()
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            def close_and_refresh():
                dialog.close()
                refresh_callback()
            
            ui.button('Done', on_click=close_and_refresh).props('color=primary')
    
    dialog.open()


def show_reorder_materials_dialog(category, refresh_callback):
    """Show dialog to reorder materials within a specific category"""
    materials = db.get_ordered_materials_in_category(category)
    
    if not materials:
        ui.notify('No materials found in this category', type='warning')
        return
    
    # Initialize the material order if not already set
    material_ids = [m['id'] for m in materials]
    db.set_material_order_in_category(category, material_ids)
    
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label(f'Reorder Materials in "{category}"').classes('text-xl font-bold mb-4')
        ui.label('Use arrows to change the order of materials').classes('text-sm text-gray-600 mb-4')
        
        # Container for the material list
        list_container = ui.column().classes('w-full gap-2')
        
        def render_list():
            list_container.clear()
            current_materials = db.get_ordered_materials_in_category(category)
            
            with list_container:
                for idx, material in enumerate(current_materials):
                    with ui.row().classes('w-full items-center gap-2 p-2 bg-gray-50 rounded'):
                        ui.label(material['name']).classes('flex-grow')
                        
                        with ui.row().classes('gap-1'):
                            # Up arrow
                            if idx > 0:
                                def move_up(mat_id=material['id']):
                                    result = db.move_material_up(mat_id)
                                    if result:
                                        render_list()
                                    else:
                                        ui.notify('Could not move material up', type='warning')
                                ui.button('↑', on_click=move_up).props('dense flat size=sm')
                            else:
                                ui.label('').classes('w-8')  # Spacer
                            
                            # Down arrow
                            if idx < len(current_materials) - 1:
                                def move_down(mat_id=material['id']):
                                    result = db.move_material_down(mat_id)
                                    if result:
                                        render_list()
                                    else:
                                        ui.notify('Could not move material down', type='warning')
                                ui.button('↓', on_click=move_down).props('dense flat size=sm')
                            else:
                                ui.label('').classes('w-8')  # Spacer
        
        render_list()
        
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            def close_and_refresh():
                dialog.close()
                refresh_callback()
            
            ui.button('Done', on_click=close_and_refresh).props('color=primary')
    
    dialog.open()



def render_materials_table(material_container, refresh_callback):
    """Render the materials table grouped by category"""
    material_container.clear()
    
    # Get ordered categories
    ordered_categories = db.get_ordered_categories()
    
    with material_container:
        # Render ordered categories first
        for category in ordered_categories:
            # Get ordered materials for this category
            items = db.get_ordered_materials_in_category(category)
            
            if items:  # Only show category if it has materials
                with ui.row().classes('w-full items-center justify-between mb-2 mt-4'):
                    ui.label(category).classes('text-2xl font-bold')
                    ui.button('↕️ Reorder', 
                             on_click=lambda cat=category: show_reorder_materials_dialog(cat, refresh_callback)).props('flat dense size=sm color=purple')
                
                with ui.grid(columns=10).classes('w-full gap-2 mb-4'):
                    # Header row
                    ui.label('Name').classes('font-bold')
                    ui.label('Status').classes('font-bold')
                    ui.label('Pricing').classes('font-bold')
                    ui.label('Pack Price').classes('font-bold')
                    ui.label('Pack Qty').classes('font-bold')
                    ui.label('Price/Item').classes('font-bold')
                    ui.label('Markup %').classes('font-bold')
                    ui.label('Final Price/Item').classes('font-bold')
                    ui.label('Supplier').classes('font-bold')
                    ui.label('Actions').classes('font-bold')
                    
                    # Material rows (already ordered)
                    for material in items:
                        render_material_row(material, refresh_callback)



def render_material_row(material, refresh_callback):
    """Render a single material row in the table"""
    is_active = material.get('is_active', 1)
    
    # Name with inactive indicator
    if is_active:
        ui.label(material['name'])
    else:
        ui.label(material['name']).classes('text-gray-400 line-through')
    
    # Status badge
    if is_active:
        ui.label('Active').classes('text-xs bg-green-100 text-green-800 px-2 py-1 rounded')
    else:
        ui.label('Inactive').classes('text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded')
    
    # Pricing type badge
    pricing_type = material.get('pricing_type', 'fixed')
    if pricing_type == 'per_kg':
        ui.label('Per g').classes('text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded')
    elif pricing_type == 'per_kg_item':
        ui.label('Per g (item)').classes('text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded')
    else:
        ui.label('Fixed').classes('text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded')
    
    # Pack price
    ui.label(format_currency(material['base_price'])).classes('text-gray-600')
    
    # Pack quantity
    pack_qty = material.get('pack_quantity', 1)
    if pack_qty > 1:
        ui.label(f"{int(pack_qty)} items").classes('text-blue-600')
    else:
        ui.label('-').classes('text-gray-400')
    
    # Price per individual item (base) - handle weight-based pricing
    pricing_type = material.get('pricing_type', 'fixed')
    if pricing_type == 'per_kg_item' and material.get('weight_per_unit'):
        # Item weight-based: price_per_gram * grams_per_item
        price_per_item = material['base_price'] * material['weight_per_unit']
    else:
        # Fixed price or bulk per_kg: divide pack price by quantity
        price_per_item = material['base_price'] / pack_qty if pack_qty > 0 else material['base_price']
    ui.label(format_currency(price_per_item)).classes('text-sm text-gray-600')
    
    # Markup
    markup = material.get('markup_percentage', 0)
    ui.label(f"{markup:.1f}%").classes('text-blue-600')
    
    # Calculate and show final price per item
    final_price_per_item = price_per_item * (1 + markup / 100)
    ui.label(format_currency(final_price_per_item)).classes('font-bold text-green-600')
    
    # Supplier with link
    if material['supplier_url']:
        ui.link(material['supplier'], material['supplier_url'], new_tab=True)
    else:
        ui.label(material['supplier'])
    
    # Actions
    with ui.row().classes('gap-0 flex-nowrap'):
        ui.button('✏️', on_click=lambda: show_edit_material_dialog(material, refresh_callback)).props('dense flat').classes('text-xl').tooltip('Edit material details')
        ui.button('🔄', on_click=lambda: update_price_from_url(material, refresh_callback)).props('dense flat color=blue').classes('text-xl').tooltip('Update price from supplier URL')
        # Toggle active/inactive button
        if is_active:
            ui.button('❌', on_click=lambda: toggle_material_status(material, refresh_callback)).props('dense flat color=orange').classes('text-xl').tooltip('Mark as Inactive (hide from purchases)')
        else:
            ui.button('✅', on_click=lambda: toggle_material_status(material, refresh_callback)).props('dense flat color=green').classes('text-xl').tooltip('Mark as Active (show in purchases)')
        ui.button('🗑️', on_click=lambda: delete_material(material, refresh_callback)).props('dense flat color=red').classes('text-xl').tooltip('Delete material permanently')


# ============ MAIN PAGE FUNCTION (Now clean and concise!) ============

def materials_page():
    """Materials management page - Clean entry point"""
    create_header()
    
    # Material table container reference
    material_container = None
    
    # Define refresh function that will be passed to all actions
    def refresh():
        render_materials_table(material_container, refresh)
    
    with ui.column().classes('w-full items-center p-4'):
        # Header with actions - AT THE TOP
        with ui.row().classes('w-full max-w-6xl items-center justify-between mb-4'):
            ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label('Materials').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                ui.button('↕️ Reorder Categories', 
                         on_click=lambda: show_reorder_categories_dialog(refresh)).props('color=purple')
                ui.button('🔄 Update All Prices', 
                         on_click=lambda: update_all_prices(refresh)).props('color=orange')
                ui.button('+ Add Material', 
                         on_click=lambda: show_add_material_dialog(refresh))
        
        # Material table container
        material_container = ui.column().classes('w-full max-w-6xl gap-4')
        
        # Initial render
        refresh()
