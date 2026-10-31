"""
Migration script to update projects table structure
Run this once to migrate from student-linked projects to independent projects
"""
import sqlite3

def migrate_projects():
    conn = sqlite3.connect('jewelry_business.db')
    cursor = conn.cursor()
    
    # Check if the old structure exists
    cursor.execute("PRAGMA table_info(projects)")
    columns = {col[1] for col in cursor.fetchall()}
    
    if 'student_id' in columns:
        print("Migrating projects table...")
        
        # Create new projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Copy data from old table (use project_name as name)
        cursor.execute('''
            INSERT INTO projects_new (id, name, description, created_at)
            SELECT id, project_name, description, created_at
            FROM projects
        ''')
        
        # Drop old table and rename new one
        cursor.execute('DROP TABLE projects')
        cursor.execute('ALTER TABLE projects_new RENAME TO projects')
        
        conn.commit()
        print("✅ Projects table migrated successfully!")
    else:
        print("✅ Projects table is already up to date")
    
    conn.close()

if __name__ == "__main__":
    migrate_projects()
