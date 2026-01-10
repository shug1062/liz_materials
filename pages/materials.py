"""Materials management page - REFACTORED for better maintainability"""
from nicegui import ui
from datetime import datetime
from database import Database
from utils import create_header, format_currency
from price_scraper import get_material_price_from_url
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
    
    if new_price:
        # Update the base price in database
        old_price = material['base_price']
        markup = material.get('markup_percentage', 0)
        
        db.update_material_price(
            material_id=material['id'],
            new_base_price=new_price,
            new_markup=markup
        )
        
        price_label = 'per g' if pricing_type == 'per_kg' else ''
        ui.notify(
            f'✅ Price updated! {format_currency(old_price)} → {format_currency(new_price)} {price_label}',
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
            ['Fixed Price', 'Per Gram (g)'],
            label='Pricing Type',
            value='Fixed Price'
        ).classes('w-full')
        ui.label('(Fixed: Standard per-item/pack price | Per g: Price shown per gram weight)').classes('text-xs text-gray-500 -mt-2')
        
        price_input = ui.number('Pack/Supplier Price (£) *', min=0, step=0.01, precision=2).classes('w-full')
        pack_qty_input = ui.number('Items in Pack', min=1, step=1, precision=0, value=1).classes('w-full')
        ui.label('(Enter 1 if sold individually, or the pack size like 50)').classes('text-xs text-gray-500 -mt-2')
        
        markup_input = ui.number('Markup Percentage (%)', min=0, max=1000, step=0.1, precision=1, value=0).classes('w-full')
        
        # Show price calculations
        ui.separator()
        price_per_item_label = ui.label('Price per item: £0.00').classes('text-sm text-gray-600')
        final_price_label = ui.label('Final Price per item: £0.00').classes('text-lg font-bold text-green-600')
        
        # Use shared price calculator to avoid duplication
        update_price_calculations = create_price_calculator(
            price_input, pack_qty_input, markup_input,
            price_per_item_label, final_price_label
        )
        
        price_input.on('update:model-value', update_price_calculations)
        pack_qty_input.on('update:model-value', update_price_calculations)
        markup_input.on('update:model-value', update_price_calculations)
        
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
                pricing_type = 'per_kg' if pricing_type_select.value == 'Per Gram (g)' else 'fixed'
                
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
                    pricing_type=pricing_type
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
        pricing_type_select = ui.select(
            ['Fixed Price', 'Per Gram (g)'],
            label='Pricing Type',
            value='Per Gram (g)' if current_pricing_type == 'per_kg' else 'Fixed Price'
        ).classes('w-full')
        
        price_input = ui.number('Pack/Supplier Price (£) *', min=0, step=0.01, precision=2, 
                               value=material['base_price']).classes('w-full')
        pack_qty_input = ui.number('Items in Pack', min=1, step=1, precision=0,
                                  value=material.get('pack_quantity', 1)).classes('w-full')
        markup_input = ui.number('Markup Percentage (%)', min=0, max=1000, step=0.1, precision=1,
                                value=material.get('markup_percentage', 0)).classes('w-full')
        
        # Show price calculations
        ui.separator()
        pack_qty = material.get('pack_quantity', 1)
        price_per_item = material['base_price'] / pack_qty if pack_qty > 0 else material['base_price']
        final_per_item = price_per_item * (1 + material.get('markup_percentage', 0) / 100)
        
        price_per_item_label = ui.label(f'Cost per item: {format_currency(price_per_item)}').classes('text-sm text-gray-600')
        final_price_label = ui.label(f'Final Price per item: {format_currency(final_per_item)}').classes('text-lg font-bold text-green-600')
        
        # Use shared price calculator to avoid duplication
        update_price_calculations = create_price_calculator(
            price_input, pack_qty_input, markup_input,
            price_per_item_label, final_price_label
        )
        
        price_input.on('update:model-value', update_price_calculations)
        pack_qty_input.on('update:model-value', update_price_calculations)
        markup_input.on('update:model-value', update_price_calculations)
        
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
                pricing_type = 'per_kg' if pricing_type_select.value == 'Per Gram (g)' else 'fixed'
                
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
                    pricing_type=pricing_type
                )
                ui.notify(f'Material {name_input.value} updated! Category: {category_value}', type='positive')
                dialog.close()
                refresh_callback()
            
            ui.button('Update Material', on_click=update_material)
    
    dialog.open()


# ============ TABLE RENDERING (Extracted for clarity) ============

def render_materials_table(material_container, refresh_callback):
    """Render the materials table grouped by category"""
    material_container.clear()
    materials = db.get_all_materials()
    
    # Group by category
    categories = {}
    for material in materials:
        cat = material['category'] or 'Uncategorized'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(material)
    
    with material_container:
        for category, items in sorted(categories.items()):
            ui.label(category).classes('text-2xl font-bold mt-4 mb-2')
            
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
                
                # Material rows
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
    
    # Price per individual item (base)
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
                ui.button('🔄 Update All Prices', 
                         on_click=lambda: update_all_prices(refresh)).props('color=orange')
                ui.button('+ Add Material', 
                         on_click=lambda: show_add_material_dialog(refresh))
        
        # Material table container
        material_container = ui.column().classes('w-full max-w-6xl gap-4')
        
        # Initial render
        refresh()
