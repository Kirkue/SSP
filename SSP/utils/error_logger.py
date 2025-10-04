"""
Centralized error logging utility.

This module provides a thread-safe way to log errors to the database
without creating multiple database connections.
"""

import threading
from database.db_manager import DatabaseManager

# Thread-local storage for database connections
_thread_local = threading.local()

def get_db_manager():
    """Get a thread-local database manager instance."""
    if not hasattr(_thread_local, 'db_manager'):
        _thread_local.db_manager = DatabaseManager()
    return _thread_local.db_manager

def log_error(error_type, message, context):
    """
    Log an error to the database in a thread-safe manner.
    
    Args:
        error_type: Type of error (e.g., "Printing Error", "Database Error")
        message: Detailed error message
        context: Context where error occurred (e.g., "printer_manager", "main_app")
    """
    try:
        db = get_db_manager()
        db.log_error(error_type, message, context)
    except Exception as e:
        print(f"Failed to log error to database: {e}")
        print(f"Original error: {error_type} - {message}")

def cleanup_db_connections():
    """Clean up all thread-local database connections."""
    try:
        if hasattr(_thread_local, 'db_manager'):
            _thread_local.db_manager.close()
            delattr(_thread_local, 'db_manager')
    except Exception as e:
        print(f"Error cleaning up database connections: {e}")

