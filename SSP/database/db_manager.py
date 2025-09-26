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
            cursor.execute("SELECT count FROM cash_inventory WHERE denomination = ?", (denomination,))
            result = cursor.fetchone()
            if result:
                new_count = result['count'] + count
                cursor.execute(
                    "UPDATE cash_inventory SET count = ?, last_updated = ? WHERE denomination = ?",
                    (new_count, datetime.now(), denomination)
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