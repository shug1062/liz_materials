"""Utility functions and shared components"""
from nicegui import ui
from datetime import datetime

# Theme colors for jewelry business
COLORS = {
    'primary': '#8B7355',  # Bronze/copper tone
    'secondary': '#C0C0C0',  # Silver
    'accent': '#FFD700',  # Gold
    'success': '#4CAF50',
    'warning': '#FF9800',
    'danger': '#F44336',
    'background': '#FAFAFA'
}


def format_currency(amount: float, precision: int = None) -> str:
    """
    Format amount as currency
    
    Args:
        amount: The amount to format
        precision: Number of decimal places. If None, auto-detects:
                  - 4 decimals for amounts < £0.01 (per-gram pricing)
                  - 2 decimals for amounts >= £0.01
    """
    if precision is None:
        # For very small amounts (per-gram pricing), show 4 decimals
        if 0 < amount < 0.01:
            precision = 4
        else:
            precision = 2
    
    return f"£{amount:.{precision}f}"


def create_header():
    """Create the main header"""
    with ui.header().classes('items-center justify-between bg-gradient-to-r from-amber-900 to-amber-700'):
        ui.label('Silver Jewellery Studio - Material Tracker').classes('text-2xl font-bold text-white')
        ui.label(f'{datetime.now().strftime("%d %B %Y")}').classes('text-white')
