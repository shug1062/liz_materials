import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import os
import shutil
from pathlib import Path

class Database:
    def __init__(self, db_path: str = "jewelry_business.db"):
        self.db_path = db_path
        self.backup_folder = "database_backups"
        self.init_database()
        self.check_and_create_backup()
    
    def get_connection(self):
        """Create a database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Students table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add class_name column if it doesn't exist
        cursor.execute("PRAGMA table_info(students)")
        student_columns = [col[1] for col in cursor.fetchall()]
        if 'class_name' not in student_columns:
            cursor.execute('ALTER TABLE students ADD COLUMN class_name TEXT')
        
        # Materials table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                unit_type TEXT NOT NULL,
                base_price REAL NOT NULL,
                pack_quantity REAL DEFAULT 1,
                markup_percentage REAL DEFAULT 0,
                supplier TEXT DEFAULT 'Cooksongold',
                supplier_url TEXT,
                is_active INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        ''')
        
        # Check if we need to migrate old data (if price_per_unit column exists)
        cursor.execute("PRAGMA table_info(materials)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'price_per_unit' in columns and 'base_price' not in columns:
            # Rename old column to base_price
            cursor.execute('ALTER TABLE materials RENAME COLUMN price_per_unit TO base_price')
            # Add markup_percentage column
            cursor.execute('ALTER TABLE materials ADD COLUMN markup_percentage REAL DEFAULT 0')
        elif 'price_per_unit' in columns:
            # Just add markup if base_price already exists
            if 'markup_percentage' not in columns:
                cursor.execute('ALTER TABLE materials ADD COLUMN markup_percentage REAL DEFAULT 0')
        
        # Add pack_quantity column if it doesn't exist
        if 'pack_quantity' not in columns:
            cursor.execute('ALTER TABLE materials ADD COLUMN pack_quantity REAL DEFAULT 1')
        
        # Add is_active column if it doesn't exist
        if 'is_active' not in columns:
            cursor.execute('ALTER TABLE materials ADD COLUMN is_active INTEGER DEFAULT 1')
        
        # Add pricing_type column if it doesn't exist ('fixed' or 'per_kg')
        if 'pricing_type' not in columns:
            cursor.execute("ALTER TABLE materials ADD COLUMN pricing_type TEXT DEFAULT 'fixed'")
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Purchases table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                project_id INTEGER,
                material_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                total_cost REAL NOT NULL,
                purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (project_id) REFERENCES projects (id),
                FOREIGN KEY (material_id) REFERENCES materials (id)
            )
        ''')
        
        # Payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                payment_method TEXT,
                notes TEXT,
                FOREIGN KEY (student_id) REFERENCES students (id)
            )
        ''')
        
        # Create indexes for better query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchases_student ON purchases(student_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchases_material ON purchases(material_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchases_project ON purchases(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_materials_active ON materials(is_active)')
        
        conn.commit()
        conn.close()
    
    # ============ BACKUP MANAGEMENT ============
    
    def check_and_create_backup(self):
        """Check if a backup is needed and create one if more than 30 days have passed"""
        # Check if database file exists
        if not os.path.exists(self.db_path):
            return  # No database to backup yet
        
        # Create backup folder if it doesn't exist
        Path(self.backup_folder).mkdir(exist_ok=True)
        
        # Check if we need a new backup
        if self._should_create_backup():
            self.create_backup()
    
    def _should_create_backup(self) -> bool:
        """Check if more than 30 days have passed since last backup"""
        # Get list of existing backups
        backups = self._get_backup_files()
        
        if not backups:
            return True  # No backups exist, create first one
        
        # Get the most recent backup
        latest_backup = max(backups, key=lambda x: x.stat().st_mtime)
        latest_backup_time = datetime.fromtimestamp(latest_backup.stat().st_mtime)
        
        # Check if 30+ days have passed
        days_since_backup = (datetime.now() - latest_backup_time).days
        return days_since_backup >= 30
    
    def _get_backup_files(self) -> list:
        """Get list of all backup files"""
        backup_path = Path(self.backup_folder)
        if not backup_path.exists():
            return []
        return list(backup_path.glob("jewelry_business_backup_*.db"))
    
    def create_backup(self) -> str:
        """Create a backup of the database with timestamp"""
        try:
            # Create backup folder if it doesn't exist
            Path(self.backup_folder).mkdir(exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"jewelry_business_backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_folder, backup_filename)
            
            # Copy the database file
            shutil.copy2(self.db_path, backup_path)
            
            print(f"✅ Database backup created: {backup_path}")
            
            # Clean up old backups (keep last 12 months)
            self._cleanup_old_backups()
            
            return backup_path
        except Exception as e:
            print(f"⚠️ Warning: Failed to create backup: {e}")
            return ""
    
    def _cleanup_old_backups(self, keep_count: int = 12):
        """Keep only the most recent N backups"""
        backups = self._get_backup_files()
        
        if len(backups) <= keep_count:
            return  # Not enough backups to clean up
        
        # Sort by modification time (oldest first)
        backups_sorted = sorted(backups, key=lambda x: x.stat().st_mtime)
        
        # Delete oldest backups, keeping only the most recent ones
        backups_to_delete = backups_sorted[:len(backups_sorted) - keep_count]
        
        for backup_file in backups_to_delete:
            try:
                backup_file.unlink()
                print(f"🗑️ Cleaned up old backup: {backup_file.name}")
            except Exception as e:
                print(f"⚠️ Warning: Could not delete old backup {backup_file.name}: {e}")
    
    def get_backup_info(self) -> Dict:
        """Get information about existing backups"""
        backups = self._get_backup_files()
        
        if not backups:
            return {
                "count": 0,
                "latest": None,
                "total_size_mb": 0,
                "backups": []
            }
        
        backup_list = []
        total_size = 0
        
        for backup_file in backups:
            size_bytes = backup_file.stat().st_size
            total_size += size_bytes
            backup_list.append({
                "filename": backup_file.name,
                "created": datetime.fromtimestamp(backup_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_mb": round(size_bytes / (1024 * 1024), 2)
            })
        
        # Sort by creation time (newest first)
        backup_list.sort(key=lambda x: x["created"], reverse=True)
        
        return {
            "count": len(backups),
            "latest": backup_list[0] if backup_list else None,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "backups": backup_list
        }
    
    # ============ STUDENTS ============
    
    def add_student(self, name: str, email: str = "", phone: str = "", notes: str = "", class_name: str = "") -> int:
        """Add a new student"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO students (name, email, phone, notes, class_name) VALUES (?, ?, ?, ?, ?)',
                (name, email, phone, notes, class_name)
            )
            student_id = cursor.lastrowid
            conn.commit()
            return student_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to add student: {e}")
        finally:
            conn.close()
    
    def get_all_students(self) -> List[Dict]:
        """Get all students"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM students ORDER BY name')
        students = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return students
    
    def get_student(self, student_id: int) -> Optional[Dict]:
        """Get a specific student"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM students WHERE id = ?', (student_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def update_student(self, student_id: int, name: str, email: str = "", phone: str = "", notes: str = "", class_name: str = ""):
        """Update student information"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE students SET name = ?, email = ?, phone = ?, notes = ?, class_name = ? WHERE id = ?',
                (name, email, phone, notes, class_name, student_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to update student: {e}")
        finally:
            conn.close()
    
    def delete_student(self, student_id: int) -> bool:
        """Delete a student and all their associated records (purchases, payments)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Delete associated purchases
            cursor.execute('DELETE FROM purchases WHERE student_id = ?', (student_id,))
            
            # Delete associated payments
            cursor.execute('DELETE FROM payments WHERE student_id = ?', (student_id,))
            
            # Delete the student
            cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to delete student: {e}")
        finally:
            conn.close()
    
    # ============ MATERIALS ============
    
    def add_material(self, name: str, category: str, unit_type: str, base_price: float,
                     pack_quantity: float = 1, markup_percentage: float = 0, 
                     supplier: str = "Cooksongold", supplier_url: str = "", notes: str = "", 
                     is_active: bool = True, pricing_type: str = "fixed") -> int:
        """Add a new material with pricing type ('fixed' or 'per_kg')"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO materials (name, category, unit_type, base_price, pack_quantity, markup_percentage, supplier, supplier_url, notes, is_active, pricing_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, category, unit_type, base_price, pack_quantity, markup_percentage, supplier, supplier_url, notes, 1 if is_active else 0, pricing_type)
            )
            material_id = cursor.lastrowid
            conn.commit()
            return material_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to add material: {e}")
        finally:
            conn.close()
    
    def get_material_final_price(self, material_id: int) -> float:
        """Calculate the final price per unit with markup"""
        material = self.get_material(material_id)
        if not material:
            return 0.0
        base_price = material['base_price']
        pack_quantity = material.get('pack_quantity', 1)
        markup = material.get('markup_percentage', 0)
        
        # Calculate price per individual item
        price_per_item = base_price / pack_quantity if pack_quantity > 0 else base_price
        
        # Apply markup
        return price_per_item * (1 + markup / 100)
        material_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return material_id
    
    def get_all_materials(self, include_inactive: bool = True) -> List[Dict]:
        """Get all materials, optionally filtering by active status"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if include_inactive:
            cursor.execute('SELECT * FROM materials ORDER BY is_active DESC, category, name')
        else:
            cursor.execute('SELECT * FROM materials WHERE is_active = 1 ORDER BY category, name')
        materials = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return materials
    
    def get_active_materials(self) -> List[Dict]:
        """Get only active materials (for purchase dropdown)"""
        return self.get_all_materials(include_inactive=False)
    
    def get_material(self, material_id: int) -> Optional[Dict]:
        """Get a specific material"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM materials WHERE id = ?', (material_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def update_material(self, material_id: int, name: str, category: str, unit_type: str, 
                       base_price: float, pack_quantity: float = 1, markup_percentage: float = 0,
                       supplier: str = "", supplier_url: str = "", notes: str = "", 
                       is_active: bool = True, pricing_type: str = "fixed"):
        """Update material information with pricing type"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE materials SET name = ?, category = ?, unit_type = ?, base_price = ?,
               pack_quantity = ?, markup_percentage = ?, supplier = ?, supplier_url = ?, 
               notes = ?, is_active = ?, pricing_type = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?''',
            (name, category, unit_type, base_price, pack_quantity, markup_percentage, 
             supplier, supplier_url, notes, 1 if is_active else 0, pricing_type, material_id)
        )
        conn.commit()
        conn.close()
    
    def toggle_material_active(self, material_id: int):
        """Toggle material active/inactive status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE materials SET is_active = NOT is_active, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (material_id,)
        )
        conn.commit()
        conn.close()
    
    def update_material_price(self, material_id: int, new_base_price: float, new_markup: float = None):
        """Update material base price and optionally markup"""
        conn = self.get_connection()
        cursor = conn.cursor()
        if new_markup is not None:
            cursor.execute(
                'UPDATE materials SET base_price = ?, markup_percentage = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
                (new_base_price, new_markup, material_id)
            )
        else:
            cursor.execute(
                'UPDATE materials SET base_price = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
                (new_base_price, material_id)
            )
        conn.commit()
        conn.close()
    
    def delete_material(self, material_id: int):
        """Delete a material"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM materials WHERE id = ?', (material_id,))
        conn.commit()
        conn.close()
    
    # ============ PROJECTS ============
    
    def add_project(self, name: str, description: str = "") -> int:
        """Add a new project (not tied to any specific student)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO projects (name, description) VALUES (?, ?)',
            (name, description)
        )
        project_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return project_id
    
    def get_all_projects(self) -> List[Dict]:
        """Get all projects with associated students and materials"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM projects ORDER BY created_at DESC')
        projects = [dict(row) for row in cursor.fetchall()]
        
        # For each project, get students and materials used
        for project in projects:
            # Get unique students working on this project
            cursor.execute('''
                SELECT DISTINCT s.id, s.name 
                FROM students s
                JOIN purchases p ON s.id = p.student_id
                WHERE p.project_id = ?
            ''', (project['id'],))
            project['students'] = [dict(row) for row in cursor.fetchall()]
            
            # Get materials used in this project
            cursor.execute('''
                SELECT m.id, m.name, SUM(p.quantity) as total_quantity, m.unit_type,
                       SUM(p.total_cost) as total_cost
                FROM materials m
                JOIN purchases p ON m.id = p.material_id
                WHERE p.project_id = ?
                GROUP BY m.id, m.name, m.unit_type
            ''', (project['id'],))
            project['materials'] = [dict(row) for row in cursor.fetchall()]
            
        conn.close()
        return projects
    
    def get_student_projects(self, student_id: int) -> List[Dict]:
        """Get all projects a student is working on"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT p.* 
            FROM projects p
            JOIN purchases pur ON p.id = pur.project_id
            WHERE pur.student_id = ?
            ORDER BY p.created_at DESC
        ''', (student_id,))
        projects = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return projects
    
    def get_project(self, project_id: int) -> Optional[Dict]:
        """Get a specific project by ID with students and materials"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
        row = cursor.fetchone()
        
        if row:
            project = dict(row)
            
            # Get students working on this project
            cursor.execute('''
                SELECT DISTINCT s.id, s.name 
                FROM students s
                JOIN purchases p ON s.id = p.student_id
                WHERE p.project_id = ?
            ''', (project_id,))
            project['students'] = [dict(row) for row in cursor.fetchall()]
            
            # Get materials used
            cursor.execute('''
                SELECT m.id, m.name, SUM(p.quantity) as total_quantity, m.unit_type,
                       SUM(p.total_cost) as total_cost
                FROM materials m
                JOIN purchases p ON m.id = p.material_id
                WHERE p.project_id = ?
                GROUP BY m.id, m.name, m.unit_type
            ''', (project_id,))
            project['materials'] = [dict(row) for row in cursor.fetchall()]
            
            conn.close()
            return project
        
        conn.close()
        return None
    
    def update_project(self, project_id: int, name: str, description: str = ""):
        """Update a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE projects 
            SET name = ?, description = ?
            WHERE id = ?
        ''', (name, description, project_id))
        conn.commit()
        conn.close()
    
    def delete_project(self, project_id: int):
        """Delete a project"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        conn.commit()
        conn.close()
    
    # ============ PURCHASES ============
    
    def add_purchase(self, student_id: int, material_id: int, quantity: float,
                    project_id: Optional[int] = None, notes: str = "", purchase_date: str = None) -> int:
        """Add a new purchase - uses final price with markup per individual item"""
        # Get current material price with markup
        material = self.get_material(material_id)
        if not material:
            raise ValueError(f"Material with id {material_id} not found")
        
        # Calculate final price per individual item with markup
        base_price = material['base_price']
        pack_quantity = material.get('pack_quantity', 1)
        markup = material.get('markup_percentage', 0)
        
        # Price per individual item
        price_per_item = base_price / pack_quantity if pack_quantity > 0 else base_price
        
        # Apply markup
        unit_price = price_per_item * (1 + markup / 100)
        total_cost = quantity * unit_price
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if purchase_date:
                cursor.execute(
                    '''INSERT INTO purchases (student_id, project_id, material_id, quantity, unit_price, total_cost, notes, purchase_date)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (student_id, project_id, material_id, quantity, unit_price, total_cost, notes, purchase_date)
                )
            else:
                cursor.execute(
                    '''INSERT INTO purchases (student_id, project_id, material_id, quantity, unit_price, total_cost, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (student_id, project_id, material_id, quantity, unit_price, total_cost, notes)
                )
            purchase_id = cursor.lastrowid
            conn.commit()
            return purchase_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to add purchase: {e}")
        finally:
            conn.close()
    
    def get_student_purchases(self, student_id: int) -> List[Dict]:
        """Get all purchases for a student with material details"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT p.*, m.name as material_name, m.unit_type, m.category,
                      pr.name as project_name
               FROM purchases p
               JOIN materials m ON p.material_id = m.id
               LEFT JOIN projects pr ON p.project_id = pr.id
               WHERE p.student_id = ?
               ORDER BY p.purchase_date DESC''',
            (student_id,)
        )
        purchases = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return purchases
    
    def get_all_purchases(self) -> List[Dict]:
        """Get all purchases with student and material details"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT p.*, s.name as student_name, m.name as material_name,
                      m.unit_type, pr.name as project_name
               FROM purchases p
               JOIN students s ON p.student_id = s.id
               JOIN materials m ON p.material_id = m.id
               LEFT JOIN projects pr ON p.project_id = pr.id
               ORDER BY p.purchase_date DESC''',
        )
        purchases = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return purchases
    
    def update_purchase(self, purchase_id: int, student_id: int, material_id: int, 
                       quantity: float, project_id: Optional[int] = None, 
                       notes: str = "", purchase_date: str = None) -> None:
        """Update an existing purchase - recalculates prices based on current material pricing"""
        # Get current material price with markup
        material = self.get_material(material_id)
        if not material:
            raise ValueError(f"Material with id {material_id} not found")
        
        # Calculate final price per individual item with markup
        base_price = material['base_price']
        pack_quantity = material.get('pack_quantity', 1)
        markup = material.get('markup_percentage', 0)
        
        # Price per individual item
        price_per_item = base_price / pack_quantity if pack_quantity > 0 else base_price
        
        # Apply markup
        unit_price = price_per_item * (1 + markup / 100)
        total_cost = quantity * unit_price
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if purchase_date:
            cursor.execute(
                '''UPDATE purchases 
                   SET student_id = ?, material_id = ?, quantity = ?, unit_price = ?, 
                       total_cost = ?, project_id = ?, notes = ?, purchase_date = ?
                   WHERE id = ?''',
                (student_id, material_id, quantity, unit_price, total_cost, 
                 project_id, notes, purchase_date, purchase_id)
            )
        else:
            cursor.execute(
                '''UPDATE purchases 
                   SET student_id = ?, material_id = ?, quantity = ?, unit_price = ?, 
                       total_cost = ?, project_id = ?, notes = ?
                   WHERE id = ?''',
                (student_id, material_id, quantity, unit_price, total_cost, 
                 project_id, notes, purchase_id)
            )
        
        conn.commit()
        conn.close()
    
    def delete_purchase(self, purchase_id: int) -> None:
        """Delete a purchase record"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM purchases WHERE id = ?', (purchase_id,))
        conn.commit()
        conn.close()
    
    # ============ PAYMENTS ============
    
    def add_payment(self, student_id: int, amount: float, payment_method: str = "", notes: str = "", payment_date: str = None) -> int:
        """Record a payment from a student"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if payment_date:
                cursor.execute(
                    'INSERT INTO payments (student_id, amount, payment_method, notes, payment_date) VALUES (?, ?, ?, ?, ?)',
                    (student_id, amount, payment_method, notes, payment_date)
                )
            else:
                cursor.execute(
                    'INSERT INTO payments (student_id, amount, payment_method, notes) VALUES (?, ?, ?, ?)',
                    (student_id, amount, payment_method, notes)
                )
            payment_id = cursor.lastrowid
            conn.commit()
            return payment_id
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to add payment: {e}")
        finally:
            conn.close()
    
    def get_student_payments(self, student_id: int) -> List[Dict]:
        """Get all payments from a student"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM payments WHERE student_id = ? ORDER BY payment_date DESC',
            (student_id,)
        )
        payments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return payments
    
    # ============ BALANCE CALCULATIONS ============
    
    def get_student_balance(self, student_id: int) -> Dict:
        """Calculate student's balance (debt/credit)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total purchases
        cursor.execute(
            'SELECT COALESCE(SUM(total_cost), 0) as total FROM purchases WHERE student_id = ?',
            (student_id,)
        )
        total_purchases = cursor.fetchone()[0]
        
        # Total payments
        cursor.execute(
            'SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE student_id = ?',
            (student_id,)
        )
        total_payments = cursor.fetchone()[0]
        
        conn.close()
        
        balance = total_payments - total_purchases
        
        return {
            'total_purchases': total_purchases,
            'total_payments': total_payments,
            'balance': balance,
            'status': 'credit' if balance > 0 else 'debt' if balance < 0 else 'settled'
        }
    
    def get_all_student_balances(self) -> List[Dict]:
        """Get balances for all students"""
        students = self.get_all_students()
        balances = []
        
        for student in students:
            balance_info = self.get_student_balance(student['id'])
            balances.append({
                'student_id': student['id'],
                'student_name': student['name'],
                **balance_info
            })
        
        return balances
