# database/db_manager.py

import sqlite3
import os
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_name="piso_print.db"):
        # Ensure the database directory exists
        db_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, db_name)
        self.conn = None
        self.connect()
        self.create_tables()

    def connect(self):
        """Establish a connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = self.dict_factory
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def dict_factory(self, cursor, row):
        """Convert query results into dictionaries."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def create_tables(self):
        """Create database tables if they don't exist."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            # Transactions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    file_name TEXT NOT NULL,
                    pages INTEGER NOT NULL,
                    copies INTEGER NOT NULL,
                    color_mode TEXT NOT NULL,
                    total_cost REAL NOT NULL,
                    amount_paid REAL NOT NULL,
                    change_given REAL NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            # Cash Inventory Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cash_inventory (
                    denomination INTEGER PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    type TEXT NOT NULL, -- 'coin' or 'bill'
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Error Log Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    context TEXT
                )
            """)
            # --- NEW: Settings Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            # --- NEW: CMYK Ink Levels Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cmyk_ink_levels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    cyan_level REAL NOT NULL,
                    magenta_level REAL NOT NULL,
                    yellow_level REAL NOT NULL,
                    black_level REAL NOT NULL,
                    last_updated DATETIME NOT NULL
                )
            """)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating tables: {e}")

    # --- NEW: get_setting method ---
    def get_setting(self, key, default=None):
        """Gets a value from the settings table."""
        if not self.conn:
            return default
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                # Attempt to convert to int, otherwise return as string
                try:
                    return int(result['value'])
                except (ValueError, TypeError):
                    return result['value']
            return default
        except sqlite3.Error as e:
            print(f"Error getting setting '{key}': {e}")
            return default

    # --- NEW: update_setting method ---
    def update_setting(self, key, value):
        """Updates or inserts a value in the settings table."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            # Use INSERT OR REPLACE to handle both new and existing keys
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating setting '{key}': {e}")

    # --- Existing Methods (assuming they are here) ---
    def log_transaction(self, data):
        if not self.conn: return
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (file_name, pages, copies, color_mode, total_cost, amount_paid, change_given, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['file_name'], data['pages'], data['copies'], data['color_mode'],
                data['total_cost'], data['amount_paid'], data['change_given'], data['status']
            ))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error logging transaction: {e}")

    def get_transaction_history(self):
        if not self.conn: return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions ORDER BY timestamp DESC")
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting transaction history: {e}")
            return []

    def update_cash_inventory(self, denomination, count, type):
        if not self.conn: return
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT count FROM cash_inventory WHERE denomination = ? AND type = ?", (denomination, type))
            result = cursor.fetchone()
            if result:
                # Set the count to the new value (not add to existing)
                cursor.execute(
                    "UPDATE cash_inventory SET count = ?, last_updated = ? WHERE denomination = ? AND type = ?",
                    (count, datetime.now(), denomination, type)
                )
            else:
                cursor.execute(
                    "INSERT INTO cash_inventory (denomination, count, type, last_updated) VALUES (?, ?, ?, ?)",
                    (denomination, count, type, datetime.now())
                )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating cash inventory: {e}")

    def get_cash_inventory(self):
        if not self.conn: return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM cash_inventory ORDER BY denomination ASC")
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting cash inventory: {e}")
            return []

    def log_error(self, error_type, message, context):
        if not self.conn: return
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO error_log (error_type, message, context) VALUES (?, ?, ?)",
                (error_type, message, context)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error logging error: {e}")

    def get_error_log(self):
        if not self.conn: return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM error_log ORDER BY timestamp DESC")
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting error log: {e}")
            return []

    # --- NEW: get_supplies_status method ---
    def get_supplies_status(self):
        """Get current paper and coin inventory status."""
        if not self.conn:
            return None
            
        try:
            cursor = self.conn.cursor()
            
            # Get paper count from settings
            cursor.execute("SELECT value FROM settings WHERE key = 'paper_count'")
            paper_result = cursor.fetchone()
            paper_count = int(paper_result['value']) if paper_result else 0
            
            # Get coin inventory
            cursor.execute("""
                SELECT denomination, count 
                FROM cash_inventory 
                WHERE type = 'coin' AND denomination IN (1, 5)
            """)
            coins = {row['denomination']: row['count'] for row in cursor.fetchall()}
            
            # Build status dictionary
            status = {
                "paper_count": paper_count,
                "coins": {
                    "peso_1": coins.get(1, 0),
                    "peso_5": coins.get(5, 0)
                },
                "warnings": []
            }
            
            # Add warnings based on thresholds
            if paper_count < 20:
                status["warnings"].append("Low paper level!")
            if coins.get(1, 0) < 50:
                status["warnings"].append("Low on ₱1 coins!")
            if coins.get(5, 0) < 20:
                status["warnings"].append("Low on ₱5 coins!")
                
            return status
            
        except sqlite3.Error as e:
            print(f"Error getting supplies status: {e}")
            return None

    def update_paper_count(self, count):
        """Update the paper count in settings."""
        self.update_setting('paper_count', count)

    # --- NEW: CMYK Ink Level Methods ---
    def get_cmyk_ink_levels(self):
        """Get the current CMYK ink levels."""
        import threading
        current_thread = threading.current_thread()
        print(f"DEBUG: get_cmyk_ink_levels called from thread: {current_thread.name} (id: {current_thread.ident})")
        print(f"DEBUG: Database connection: {self.conn}")
        
        if not self.conn:
            print("DEBUG: No database connection available")
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT cyan_level, magenta_level, yellow_level, black_level, last_updated
                FROM cmyk_ink_levels 
                ORDER BY last_updated DESC 
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                try:
                    return {
                        'cyan': float(result['cyan_level']),
                        'magenta': float(result['magenta_level']),
                        'yellow': float(result['yellow_level']),
                        'black': float(result['black_level']),
                        'last_updated': result['last_updated']
                    }
                except (ValueError, TypeError) as e:
                    print(f"Error converting CMYK values from database: {e}")
                    print(f"Raw values: cyan={result['cyan_level']}, magenta={result['magenta_level']}, yellow={result['yellow_level']}, black={result['black_level']}")
                    # Return default values if conversion fails
                    return {
                        'cyan': 100.0,
                        'magenta': 100.0,
                        'yellow': 100.0,
                        'black': 100.0,
                        'last_updated': result['last_updated']
                    }
            return None
        except sqlite3.Error as e:
            print(f"Error getting CMYK ink levels: {e}")
            return None

    def update_cmyk_ink_levels(self, cyan, magenta, yellow, black):
        """Update CMYK ink levels with decimal precision."""
        if not self.conn:
            return False
        try:
            # Ensure values are properly converted to float
            cyan_float = float(cyan)
            magenta_float = float(magenta)
            yellow_float = float(yellow)
            black_float = float(black)
            
            print(f"DEBUG: Storing CMYK values as floats: C:{cyan_float}, M:{magenta_float}, Y:{yellow_float}, K:{black_float}")
            
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO cmyk_ink_levels (cyan_level, magenta_level, yellow_level, black_level, timestamp, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cyan_float, magenta_float, yellow_float, black_float, datetime.now(), datetime.now()))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error updating CMYK ink levels: {e}")
            return False
        except ValueError as e:
            print(f"Error converting CMYK values to float: {e}")
            return False

    def get_cmyk_ink_history(self, limit=10):
        """Get CMYK ink level history."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT cyan_level, magenta_level, yellow_level, black_level, last_updated
                FROM cmyk_ink_levels 
                ORDER BY last_updated DESC 
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting CMYK ink history: {e}")
            return []

    def get_supplies_status_with_cmyk(self):
        """Get current supplies status including CMYK ink levels."""
        if not self.conn:
            return None
            
        try:
            cursor = self.conn.cursor()
            
            # Get paper count from settings
            cursor.execute("SELECT value FROM settings WHERE key = 'paper_count'")
            paper_result = cursor.fetchone()
            paper_count = int(paper_result['value']) if paper_result else 0
            
            # Get coin inventory
            cursor.execute("""
                SELECT denomination, count 
                FROM cash_inventory 
                WHERE type = 'coin' AND denomination IN (1, 5)
            """)
            coins = {row['denomination']: row['count'] for row in cursor.fetchall()}
            
            # Get CMYK ink levels
            cmyk_levels = self.get_cmyk_ink_levels()
            
            # Build status dictionary
            status = {
                "paper_count": paper_count,
                "coins": {
                    "peso_1": coins.get(1, 0),
                    "peso_5": coins.get(5, 0)
                },
                "cmyk_levels": cmyk_levels,
                "warnings": []
            }
            
            # Add warnings based on thresholds
            if paper_count < 20:
                status["warnings"].append("Low paper level!")
            if coins.get(1, 0) < 50:
                status["warnings"].append("Low on ₱1 coins!")
            if coins.get(5, 0) < 20:
                status["warnings"].append("Low on ₱5 coins!")
            
            # Add CMYK ink warnings
            if cmyk_levels:
                if cmyk_levels['cyan'] < 10.0:
                    status["warnings"].append("Low Cyan ink level!")
                if cmyk_levels['magenta'] < 10.0:
                    status["warnings"].append("Low Magenta ink level!")
                if cmyk_levels['yellow'] < 10.0:
                    status["warnings"].append("Low Yellow ink level!")
                if cmyk_levels['black'] < 10.0:
                    status["warnings"].append("Low Black ink level!")
                
            return status
            
        except sqlite3.Error as e:
            print(f"Error getting supplies status with CMYK: {e}")
            return None