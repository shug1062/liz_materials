"""Shared UI helper functions for reducing code duplication"""
from utils import format_currency


def create_price_calculator(price_input, pack_qty_input, markup_input, 
                            price_per_item_label, final_price_label,
                            pricing_type_select=None, weight_input=None):
    """
    Create a reusable price calculation function that updates UI labels.
    
    This function is used in both add and edit material dialogs to avoid duplication.
    Supports both fixed pricing and weight-based pricing.
    
    Args:
        price_input: NiceGUI input for base/pack price
        pack_qty_input: NiceGUI input for pack quantity
        markup_input: NiceGUI input for markup percentage
        price_per_item_label: NiceGUI label to display cost per item
        final_price_label: NiceGUI label to display final price per item
        pricing_type_select: (Optional) NiceGUI select for pricing type
        weight_input: (Optional) NiceGUI input for weight per unit (grams)
        
    Returns:
        Function that performs the calculation and updates labels
    """
    def calculate_and_update():
        """Calculate prices and update UI labels"""
        if price_input.value and pack_qty_input.value and markup_input.value is not None:
            pack_price = price_input.value
            pack_qty = pack_qty_input.value if pack_qty_input.value > 0 else 1
            
            # Determine pricing type
            is_weight_based = False
            if pricing_type_select:
                is_weight_based = pricing_type_select.value == 'Per Gram (g)'
            
            # Calculate cost per individual item
            if is_weight_based and weight_input and weight_input.value:
                # Weight-based pricing: price_per_gram * grams_per_item
                price_per_item = pack_price * weight_input.value
            else:
                # Fixed pricing: divide pack price by quantity
                price_per_item = pack_price / pack_qty
            
            # Apply markup to get final price
            final_per_item = price_per_item * (1 + markup_input.value / 100)
            
            # Update UI labels
            price_per_item_label.text = f'Cost per item: {format_currency(price_per_item)}'
            final_price_label.text = f'Final Price per item: {format_currency(final_per_item)}'
    
    return calculate_and_update


def calculate_material_prices(base_price: float, pack_quantity: float, markup_percentage: float) -> dict:
    """
    Calculate material pricing breakdown.
    
    Args:
        base_price: Base price for the pack/unit
        pack_quantity: Number of items in pack (1 for individual items)
        markup_percentage: Markup percentage to apply
        
    Returns:
        Dict with 'price_per_item', 'final_per_item', and 'markup_amount'
    """
    pack_qty = pack_quantity if pack_quantity > 0 else 1
    price_per_item = base_price / pack_qty
    markup_amount = price_per_item * (markup_percentage / 100)
    final_per_item = price_per_item + markup_amount
    
    return {
        'price_per_item': price_per_item,
        'final_per_item': final_per_item,
        'markup_amount': markup_amount
    }
