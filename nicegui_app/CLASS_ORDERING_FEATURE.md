# Class Ordering Feature

## Overview
Added the ability to customize the order in which classes appear on the Students page.

## What's New

### 1. Reorder Classes Button
- A new **"⚙️ Reorder Classes"** button appears at the top of the Students page (next to "Add Student")
- Click this button to open the class ordering dialog

### 2. Class Ordering Dialog
- Shows all your classes in their current order
- Use **↑** (up arrow) and **↓** (down arrow) buttons to move classes up or down
- Click **"Save Order"** to save your preferred order
- Click **"Cancel"** to discard changes

### 3. Custom Display Order
- Classes now appear in your custom order on the Students page
- New classes that haven't been ordered yet appear alphabetically at the end
- "No Class Assigned" always appears last

## How to Use

1. Go to the **Students** page
2. Click the **"⚙️ Reorder Classes"** button
3. Use the arrow buttons to arrange classes in your preferred order:
   - **↑** moves a class up (higher priority)
   - **↓** moves a class down (lower priority)
4. Click **"Save Order"** when you're happy with the arrangement
5. The Students page will refresh showing classes in your new order

## Technical Details

### Database Changes
- New table: `class_order` stores the custom ordering
  - `class_name`: The name of the class
  - `sort_order`: The position in the list (0 = first, 1 = second, etc.)

### New Database Methods
- `get_class_order()`: Get the current ordering as a dictionary
- `get_ordered_classes()`: Get class names in custom order
- `set_class_order(class_names)`: Save a new custom order
- `move_class_up(class_name)`: Move a class up one position
- `move_class_down(class_name)`: Move a class down one position

### File Changes
- **database.py**: Added `class_order` table and ordering methods
- **pages/students.py**: 
  - Added "Reorder Classes" button
  - Added reorder dialog with arrow controls
  - Updated class display logic to use custom ordering

## Example Use Case

If you have classes like:
- Monday Morning
- Monday Afternoon
- Tuesday Morning
- Wednesday Evening

You can reorder them to appear in chronological order, or group them by importance, or any other preference you have. The order you set will persist across sessions.

## Notes

- The ordering only affects the display on the Students page
- Individual students within each class are still shown in their original order
- The "No Class Assigned" group always appears last and cannot be reordered
- When you add a new class (by adding a student with a new class name), it will appear alphabetically at the end until you manually order it
