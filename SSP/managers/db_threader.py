"""
Database Threader

Manages database operations in a dedicated thread to avoid SQLite thread safety issues.
Provides a queue-based system for executing database operations asynchronously and
emitting signals when operations complete.

Key Features:
- Thread-safe database operations
- Queue-based operation management
- Signal emissions for real-time UI updates
- Support for CMYK ink levels, paper count, and coin inventory
"""

import sqlite3
import threading
import queue
import time
from PyQt5.QtCore import QObject, pyqtSignal
from database.db_manager import DatabaseManager


class DatabaseOperation:
    """
    Represents a database operation to be executed in the dedicated thread.
    
    Attributes:
        operation_type: Type of operation (e.g., 'get_cmyk_levels', 'update_paper_count')
        data: Dictionary of operation parameters
        callback: Optional callback function called when operation completes
        result: Operation result (set after execution)
        error: Error message if operation fails
    """
    
    def __init__(self, operation_type, data, callback=None):
        self.operation_type = operation_type
        self.data = data
        self.callback = callback
        self.result = None
        self.error = None


class DatabaseThreadManager(QObject):
    """
    Manages database operations in a dedicated thread.
    
    All database operations are queued and executed sequentially in a background
    thread to ensure SQLite thread safety and prevent blocking the GUI.
    
    Signals:
        cmyk_levels_updated(dict): Emits updated CMYK levels {C, M, Y, K: float}
        paper_count_updated(int): Emits updated paper count
        coin_count_updated(int, int): Emits coin counts (₱1, ₱5)
        operation_completed(str, bool): Emits operation type and success status
    """
    
    # Signals for real-time updates
    cmyk_levels_updated = pyqtSignal(dict)
    paper_count_updated = pyqtSignal(int)
    coin_count_updated = pyqtSignal(int, int)
    operation_completed = pyqtSignal(str, bool)
    
    def __init__(self):
        """Initialize the database thread manager."""
        super().__init__()
        self.operation_queue = queue.Queue()
        self.db_manager = None
        self.thread = None
        self.running = False
        
    def start(self):
        """Start the database worker thread."""
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._database_worker, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop the database worker thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
    
    def _database_worker(self):
        """
        Worker method that runs in the dedicated database thread.
        
        Creates database connection and processes queued operations sequentially.
        """
        # Create database manager in this thread (for thread safety)
        self.db_manager = DatabaseManager()
        
        while self.running:
            try:
                # Get operation from queue with timeout
                operation = self.operation_queue.get(timeout=0.1)
                
                # Route operation to appropriate handler
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
                elif operation.operation_type == "update_coin_inventory":
                    self._handle_update_coin_inventory(operation)
                else:
                    operation.error = f"Unknown operation type: {operation.operation_type}"
                
                # Execute callback if provided
                if operation.callback:
                    operation.callback(operation)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error in database worker: {e}")
                if operation and operation.callback:
                    operation.error = str(e)
                    operation.callback(operation)
    
    def _handle_get_cmyk_levels(self, operation):
        """Retrieve CMYK ink levels from database."""
        try:
            result = self.db_manager.get_cmyk_ink_levels()
            operation.result = result
            if result:
                self.cmyk_levels_updated.emit(result)
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error getting CMYK levels: {e}")
    
    def _handle_update_cmyk_levels(self, operation):
        """Update CMYK ink levels in database."""
        try:
            cyan = operation.data['cyan']
            magenta = operation.data['magenta']
            yellow = operation.data['yellow']
            black = operation.data['black']
            
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
            print(f"❌ Error updating CMYK levels: {e}")
    
    def _handle_get_paper_count(self, operation):
        """Retrieve paper count from database."""
        try:
            result = self.db_manager.get_setting('paper_count', default=100)
            operation.result = result
            self.paper_count_updated.emit(result)
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error getting paper count: {e}")
    
    def _handle_update_paper_count(self, operation):
        """Update paper count in database."""
        try:
            count = operation.data['count']
            self.db_manager.update_setting('paper_count', count)
            operation.result = True
            self.paper_count_updated.emit(count)
            self.operation_completed.emit("update_paper_count", True)
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error updating paper count: {e}")
    
    def _handle_get_coin_counts(self, operation):
        """Retrieve coin counts from database."""
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
            print(f"❌ Error getting coin counts: {e}")
    
    def _handle_update_coin_counts(self, operation):
        """Update coin counts in database."""
        try:
            denomination = operation.data['denomination']
            count = operation.data['count']
            coin_type = operation.data['type']
            
            self.db_manager.update_cash_inventory(denomination, count, coin_type)
            operation.result = True
            self.operation_completed.emit("update_coin_counts", True)
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error updating coin counts: {e}")
    
    def _handle_update_coin_inventory(self, operation):
        """Update coin inventory after dispensing change."""
        try:
            coins_1 = operation.data['coins_1']
            coins_5 = operation.data['coins_5']
            
            # Get current inventory
            inventory = self.db_manager.get_cash_inventory()
            current_1 = 0
            current_5 = 0
            
            for item in inventory:
                if item['denomination'] == 1 and item['type'] == 'coin':
                    current_1 = item['count']
                elif item['denomination'] == 5 and item['type'] == 'coin':
                    current_5 = item['count']
            
            # Calculate new counts (prevent negative)
            new_1 = max(0, current_1 - coins_1)
            new_5 = max(0, current_5 - coins_5)
            
            # Update inventory
            self.db_manager.update_cash_inventory(1, new_1, 'coin')
            self.db_manager.update_cash_inventory(5, new_5, 'coin')
            
            operation.result = {'coins_1': new_1, 'coins_5': new_5}
            self.operation_completed.emit("update_coin_inventory", True)
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error updating coin inventory: {e}")
    
    # Public methods for queuing operations
    
    def get_cmyk_levels(self, callback=None):
        """
        Queue operation to get CMYK ink levels.
        
        Args:
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("get_cmyk_levels", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_cmyk_levels(self, cyan, magenta, yellow, black, callback=None):
        """
        Queue operation to update CMYK ink levels.
        
        Args:
            cyan: Cyan level (0-100)
            magenta: Magenta level (0-100)
            yellow: Yellow level (0-100)
            black: Black level (0-100)
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("update_cmyk_levels", {
            'cyan': cyan, 'magenta': magenta, 'yellow': yellow, 'black': black
        }, callback)
        self.operation_queue.put(operation)
        return operation
    
    def get_paper_count(self, callback=None):
        """
        Queue operation to get paper count.
        
        Args:
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("get_paper_count", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_paper_count(self, count, callback=None):
        """
        Queue operation to update paper count.
        
        Args:
            count: New paper count
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("update_paper_count", {'count': count}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_coin_inventory(self, coins_1, coins_5, callback=None):
        """
        Queue operation to update coin inventory (deduct dispensed coins).
        
        Args:
            coins_1: Number of ₱1 coins to deduct
            coins_5: Number of ₱5 coins to deduct
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("update_coin_inventory", {
            'coins_1': coins_1, 'coins_5': coins_5
        }, callback)
        self.operation_queue.put(operation)
        return operation
    
    def get_coin_counts(self, callback=None):
        """
        Queue operation to get coin counts.
        
        Args:
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("get_coin_counts", {}, callback)
        self.operation_queue.put(operation)
        return operation
    
    def update_coin_counts(self, denomination, count, coin_type, callback=None):
        """
        Queue operation to update coin counts.
        
        Args:
            denomination: Coin denomination (1 or 5)
            count: New count
            coin_type: 'coin' type
            callback: Optional callback function(operation)
            
        Returns:
            DatabaseOperation object
        """
        operation = DatabaseOperation("update_coin_counts", {
            'denomination': denomination, 'count': count, 'type': coin_type
        }, callback)
        self.operation_queue.put(operation)
        return operation

