"""Projects management page"""
from nicegui import ui
from database import Database
from utils import create_header, format_currency, COLORS

db = Database()


def projects_page():
    """Projects management page"""
    create_header()
    
    with ui.column().classes('w-full items-center p-4'):
        with ui.row().classes('w-full max-w-6xl items-center justify-between mb-4'):
            ui.button('← Back to Dashboard', on_click=lambda: ui.navigate.to('/')).props('flat')
            ui.label('Projects').classes('text-3xl font-bold')
            ui.button('+ Add Project', on_click=lambda: show_add_project_dialog())
        
        # Container for projects list
        projects_container = ui.column().classes('w-full max-w-6xl gap-4')
        
        def refresh_projects():
            """Refresh the projects list"""
            projects_container.clear()
            
            with projects_container:
                projects = db.get_all_projects()
                
                if not projects:
                    ui.label('No projects yet. Add your first project!').classes('text-gray-500')
                else:
                    with ui.grid(columns=6).classes('w-full gap-2 mb-4'):
                        ui.label('Project Name').classes('font-bold')
                        ui.label('Description').classes('font-bold')
                        ui.label('Students').classes('font-bold')
                        ui.label('Total Cost').classes('font-bold')
                        ui.label('Avg Cost/Student').classes('font-bold')
                        ui.label('Actions').classes('font-bold')
                        
                        for project in projects:
                            # Project name
                            ui.label(project['name']).classes('font-bold')
                            
                            # Description
                            desc = project.get('description', '') or '-'
                            ui.label(desc[:50] + '...' if len(desc) > 50 else desc).classes('text-sm text-gray-600')
                            
                            # Students working on this project
                            students = project.get('students', [])
                            student_count = len(students)
                            if students:
                                with ui.column().classes('gap-1'):
                                    for student in students[:3]:  # Show first 3
                                        ui.link(student['name'], f"/student/{student['id']}").classes('text-blue-600 text-sm')
                                    if len(students) > 3:
                                        ui.label(f'+{len(students) - 3} more').classes('text-xs text-gray-500')
                            else:
                                ui.label('No students yet').classes('text-gray-400 text-sm')
                            
                            # Calculate total project cost
                            materials = project.get('materials', [])
                            total_cost = sum(mat.get('total_cost', 0) or 0 for mat in materials)
                            
                            # Total cost column
                            if total_cost > 0:
                                ui.label(format_currency(total_cost)).classes('font-bold text-lg')
                            else:
                                ui.label('-').classes('text-gray-400')
                            
                            # Average cost per student column
                            if student_count > 0 and total_cost > 0:
                                avg_cost = total_cost / student_count
                                ui.label(format_currency(avg_cost)).classes('font-bold text-lg text-blue-600')
                            else:
                                ui.label('-').classes('text-gray-400')
                            
                            # Actions
                            with ui.row():
                                ui.button('✏️', on_click=lambda p=project: show_edit_project_dialog(p)).props('dense flat')
                                ui.button('🗑️', on_click=lambda p=project: delete_project(p)).props('dense flat color=red')
        
        def show_add_project_dialog():
            """Show dialog to add a new project"""
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Add New Project').classes('text-xl font-bold mb-4')
                
                name_input = ui.input('Project Name *', placeholder='e.g., Silver Ring, Pendant').classes('w-full')
                description_input = ui.textarea('Description', 
                                               placeholder='Brief description of the project...').classes('w-full')
                
                ui.label('💡 Tip: Students and materials will be automatically tracked when purchases are recorded for this project.').classes('text-sm text-blue-600 mt-2')
                
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    
                    def add_project():
                        if not name_input.value:
                            ui.notify('Please enter a project name', type='warning')
                            return
                        
                        db.add_project(
                            name=name_input.value,
                            description=description_input.value or ""
                        )
                        ui.notify(f'Project "{name_input.value}" added successfully!', type='positive')
                        dialog.close()
                        refresh_projects()
                    
                    ui.button('Add Project', on_click=add_project).props('color=primary')
            
            dialog.open()
        
        def show_edit_project_dialog(project):
            """Show dialog to edit a project"""
            with ui.dialog() as dialog, ui.card().classes('w-96'):
                ui.label('Edit Project').classes('text-xl font-bold mb-4')
                
                name_input = ui.input('Project Name *', value=project['name']).classes('w-full')
                description_input = ui.textarea('Description', 
                                               value=project.get('description', '') or "").classes('w-full')
                
                # Show current students and materials (read-only info)
                students = project.get('students', [])
                materials = project.get('materials', [])
                
                if students or materials:
                    ui.separator()
                    ui.label('Current Activity').classes('text-sm font-bold text-gray-700 mt-2')
                    
                    if students:
                        ui.label(f"Students: {', '.join([s['name'] for s in students])}").classes('text-sm text-gray-600')
                    
                    if materials:
                        ui.label(f"Materials: {len(materials)} different materials used").classes('text-sm text-gray-600')
                
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    
                    def update_project():
                        if not name_input.value:
                            ui.notify('Please enter a project name', type='warning')
                            return
                        
                        db.update_project(
                            project_id=project['id'],
                            name=name_input.value,
                            description=description_input.value or ""
                        )
                        ui.notify(f'Project "{name_input.value}" updated successfully!', type='positive')
                        dialog.close()
                        refresh_projects()
                    
                    ui.button('Update', on_click=update_project).props('color=primary')
            
            dialog.open()
        
        def delete_project(project):
            """Delete a project"""
            with ui.dialog() as dialog, ui.card():
                ui.label(f'Delete project "{project["name"]}"?').classes('text-lg')
                ui.label('⚠️ This will not delete associated purchases.').classes('text-sm text-orange-600 mb-4')
                
                with ui.row().classes('gap-2'):
                    ui.button('Cancel', on_click=dialog.close).props('flat')
                    
                    def confirm_delete():
                        db.delete_project(project['id'])
                        ui.notify(f'Project "{project["name"]}" deleted', type='positive')
                        dialog.close()
                        refresh_projects()
                    
                    ui.button('Delete', on_click=confirm_delete).props('color=red')
            
            dialog.open()
        
        # Initial load
        refresh_projects()
