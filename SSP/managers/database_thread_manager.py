#!/usr/bin/env python3
"""
Database Thread Manager - Manages database operations in dedicated threads.
"""

import sqlite3
import threading
import queue
import time
from PyQt5.QtCore import QObject, pyqtSignal
from database.db_manager import DatabaseManager

class DatabaseOperation:
    """Represents a database operation to be executed."""
    def __init__(self, operation_type, data, callback=None):
        self.operation_type = operation_type
        self.data = data
        self.callback = callback
        self.result = None
        self.error = None

class DatabaseThreadManager(QObject):
    """
    Manages database operations in a dedicated thread to avoid SQLite thread safety issues.
    """
    
    # Signals for different operations
    cmyk_levels_updated = pyqtSignal(dict)  # Emits updated CMYK levels
    paper_count_updated = pyqtSignal(int)   # Emits updated paper count
    coin_count_updated = pyqtSignal(int, int)  # Emits coin counts
    operation_completed = pyqtSignal(str, bool)  # Emits operation type and success
    
    def __init__(self):
        super().__init__()
        self.operation_queue = queue.Queue()
        self.db_manager = None
        self.thread = None
        self.running = False
        
    def start(self):
        """Start the database thread."""
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._database_worker, daemon=True)
            self.thread.start()
            print("Database thread manager started")
    
    def stop(self):
        """Stop the database thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        print("Database thread manager stopped")
    
    def _database_worker(self):
        """Worker method that runs in the dedicated database thread."""
        print(f"Database worker started in thread: {threading.current_thread().name}")
        
        # Create database manager in this thread
        self.db_manager = DatabaseManager()
        print(f"Database manager created in thread: {threading.current_thread().name}")
        
        while self.running:
            try:
                # Get operation from queue with timeout
                operation = self.operation_queue.get(timeout=0.1)
                
                if operation.operation_type == "get_cmyk_levels":
                    self._handle_get_cmyk_levels(operation)
                elif operation.operation_type == "update_cmyk_levels":
                    self._handle_update_cmyk_levels(operation)
                elif operation.operation_type == "get_paper_count":
                    self._handle_get_paper_count(operation)
                elif operation.operation_type == "update_paper_count":
                    self._handle_update_paper_count(operation)
                elif operation.operation_type == "get_coin_counts":
                    self._handle_get_coin_counts(operation)
                elif operation.operation_type == "update_coin_counts":
                    self._handle_update_coin_counts(operation)
                else:
                    print(f"Unknown operation type: {operation.operation_type}")
                    operation.error = f"Unknown operation type: {operation.operation_type}"
                
                # Call callback if provided
                if operation.callback:
                    operation.callback(operation)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in database worker: {e}")
                if operation and operation.callback:
                    operation.error = str(e)
                    operation.callback(operation)
    
    def _handle_get_cmyk_levels(self, operation):
        """Handle getting CMYK levels."""
        try:
            result = self.db_manager.get_cmyk_ink_levels()
            operation.result = result
            if result:
                self.cmyk_levels_updated.emit(result)
        except Exception as e:
            operation.error = str(e)
            print(f"Error getting CMYK levels: {e}")
    
    def _handle_update_cmyk_levels(self, operation):
        """Handle updating CMYK levels."""
        try:
            cyan, magenta, yellow, black = operation.data['cyan'], operation.data['magenta'], operation.data['yellow'], operation.data['black']
            success = self.db_manager.update_cmyk_ink_levels(cyan, magenta, yellow, black)
            operation.result = success
            if success:
                # Get updated levels and emit signal
                updated_levels = self.db_manager.get_cmyk_ink_levels()
                if updated_levels:
                    self.cmyk_levels_updated.emit(updated_levels)
            self.operation_completed.emit("update_cmyk_levels", success)
        except Exception as e:
            operation.error = str(e)
            print(f"Error updating CMYK levels: {e}")
    
    def _handle_get_paper_count(self, operation):
        """Handle getting paper count."""
        try:
            result = self.db_manager.get_setting('paper_count', default=100)
            operation.result = result
            self.paper_count_updated.emit(result)
        except Exception as e:
            operation.error = str(e)
            print(f"Error getting paper count: {e}")
    
    def _handle_update_paper_count(self, operation):
        """Handle updating paper count."""
        try:
            count = operation.data['count']
            self.db_manager.update_setting('paper_count', count)
            operation.result = True
            self.paper_count_updated.emit(count)
            self.operation_completed.emit("update_paper_count", True)
        except Exception as e:
            operation.error = str(e)
            print(f"Error updating paper count: {e}")
    
    def _handle_get_coin_counts(self, operation):
        """Handle getting coin counts."""
        try:
            inventory = self.db_manager.get_cash_inventory()
            coin_1_count = 0
            coin_5_count = 0
            
            for item in inventory:
                if item['denomination'] == 1 and item['type'] == 'coin':
                    coin_1_count = item['count']
                elif item['denomination'] == 5 and item['type'] == 'coin':
                    coin_5_count = item['count']
            
            operation.result = (coin_1_count, coin_5_count)
            self.coin_count_updated.emit(coin_1_count, coin_5_count)
        except Exception as e:
            operation.error = str(e)
            print(f"Error getting coin counts: {e}")
    
    def _handle_update_coin_counts(self, operation):
        """Handle updating coin counts."""
        try:
            denomination, count, coin_type = operation.data['denomination'], operation.data['count'], operation.data['type']
            self.db_manager.update_cash_inventory(denomination, count, coin_type)
            operation.result = True
            self.operation_completed.emit("update_coin_counts", True)
        except Exception as e:
            operation.error = str(e)
            print(f"Error updating coin counts: {e}")
    
    # Public methods for queuing operations
    def get_cmyk_levels(self, callback=None):
        """Queue a get CMYK levels operation."""
        operation = DatabaseOperation("get_cmyk_levels", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_cmyk_levels(self, cyan, magenta, yellow, black, callback=None):
        """Queue an update CMYK levels operation."""
        operation = DatabaseOperation("update_cmyk_levels", {
            'cyan': cyan, 'magenta': magenta, 'yellow': yellow, 'black': black
        }, callback)
        self.operation_queue.put(operation)
        return operation
    
    def get_paper_count(self, callback=None):
        """Queue a get paper count operation."""
        operation = DatabaseOperation("get_paper_count", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_paper_count(self, count, callback=None):
        """Queue an update paper count operation."""
        operation = DatabaseOperation("update_paper_count", {'count': count}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def get_coin_counts(self, callback=None):
        """Queue a get coin counts operation."""
        operation = DatabaseOperation("get_coin_counts", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_coin_counts(self, denomination, count, coin_type, callback=None):
        """Queue an update coin counts operation."""
        operation = DatabaseOperation("update_coin_counts", {
            'denomination': denomination, 'count': count, 'type': coin_type
        }, callback)
        self.operation_queue.put(operation)
        return operation
