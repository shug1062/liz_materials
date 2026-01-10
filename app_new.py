"""
Silver Jewellery Studio - Material Tracker
Main application entry point (refactored version)
"""
from nicegui import ui
from typing import Optional

# Import all page functions
from pages.dashboard import dashboard_page
from pages.students import students_page, student_detail_page
from pages.materials import materials_page
from pages.projects import projects_page
from pages.purchases import purchases_page
from pages.payments import payments_page


# Register all pages
@ui.page('/')
def index():
    dashboard_page()


@ui.page('/students')
def students(class_name: Optional[str] = None):
    students_page(selected_class=class_name)


@ui.page('/student/{student_id}')
def student_detail(student_id: int):
    student_detail_page(student_id)


@ui.page('/materials')
def materials():
    materials_page()


@ui.page('/projects')
def projects():
    projects_page()


@ui.page('/purchases')
def purchases():
    purchases_page()


@ui.page('/payments')
def payments():
    payments_page()


# Run the app
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Silver Jewellery Studio Tracker', port=8080, reload=False)
