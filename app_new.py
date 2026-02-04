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
from pages.payments_report import payments_report_page


# Register all pages
@ui.page('/')
def index():
    dashboard_page()


@ui.page('/students')
def students(class_name: Optional[str] = None):
    students_page(selected_class=class_name)


@ui.page('/student/{student_id}')
def student_detail(student_id: int, class_name: str = None):
    student_detail_page(student_id, class_name)


@ui.page('/materials')
def materials():
    materials_page()


@ui.page('/projects')
def projects():
    projects_page()


@ui.page('/purchases')
def purchases(class_name: Optional[str] = None, student_id: Optional[int] = None, return_to: Optional[str] = None):
    purchases_page(selected_class=class_name, selected_student_id=student_id, return_to=return_to)


@ui.page('/payments')
def payments(class_name: Optional[str] = None, student_id: Optional[int] = None, return_to: Optional[str] = None):
    payments_page(selected_class=class_name, selected_student_id=student_id, return_to=return_to)


@ui.page('/payments_report')
def payments_report(filter: Optional[str] = None):
    payments_report_page(filter_type=filter)


# Run the app
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Silver Jewellery Studio Tracker', port=8080, reload=True)
