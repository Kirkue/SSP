#!/usr/bin/env python3
"""
Script to fix corrupted CMYK data in the database.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager

def fix_cmyk_database():
    """Fix corrupted CMYK data in the database."""
    print("=== Fixing CMYK Database ===")
    
    # Initialize database manager
    db_manager = DatabaseManager()
    
    # Clear all existing CMYK data
    print("1. Clearing existing CMYK data...")
    try:
        cursor = db_manager.conn.cursor()
        cursor.execute("DELETE FROM cmyk_ink_levels")
        db_manager.conn.commit()
        print("   Existing CMYK data cleared")
    except Exception as e:
        print(f"   Error clearing data: {e}")
    
    # Insert fresh CMYK data
    print("2. Inserting fresh CMYK data...")
    try:
        success = db_manager.update_cmyk_ink_levels(100.0, 100.0, 100.0, 100.0)
        if success:
            print("   Fresh CMYK data inserted successfully")
        else:
            print("   Failed to insert fresh CMYK data")
    except Exception as e:
        print(f"   Error inserting data: {e}")
    
    # Verify the data
    print("3. Verifying CMYK data...")
    try:
        levels = db_manager.get_cmyk_ink_levels()
        if levels:
            print(f"   Current levels: C:{levels['cyan']:.1f}% M:{levels['magenta']:.1f}% Y:{levels['yellow']:.1f}% K:{levels['black']:.1f}%")
        else:
            print("   No CMYK data found")
    except Exception as e:
        print(f"   Error verifying data: {e}")
    
    print("=== CMYK Database Fix Complete ===")

if __name__ == "__main__":
    fix_cmyk_database()
