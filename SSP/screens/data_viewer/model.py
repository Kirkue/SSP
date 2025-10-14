# screens/data_viewer/model.py

from PyQt5.QtCore import QObject, pyqtSignal
from database.db_manager import DatabaseManager

class DataViewerModel(QObject):
    """Handles the data and business logic for the data viewer screen."""
    transactions_loaded = pyqtSignal(list)      # Emits list of transactions
    cash_inventory_loaded = pyqtSignal(list)    # Emits list of cash inventory
    error_log_loaded = pyqtSignal(list)         # Emits list of error logs
    show_message = pyqtSignal(str, str)         # Emits message title and text
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
    
    def load_transactions(self):
        """Loads transaction history from the database."""
        try:
            print("🔄 Loading transactions from database...")
            transactions = self.db_manager.get_transaction_history()
            print(f"✅ Loaded {len(transactions)} transactions")
            self.transactions_loaded.emit(transactions)
        except Exception as e:
            print(f"❌ ERROR: Failed to load transactions: {e}")
            self.show_message.emit("Error", f"Failed to load transactions: {str(e)}")
    
    def load_cash_inventory(self):
        """Loads cash inventory from the database."""
        try:
            print("🔄 Loading cash inventory from database...")
            inventory = self.db_manager.get_cash_inventory()
            print(f"✅ Loaded {len(inventory)} cash inventory items")
            self.cash_inventory_loaded.emit(inventory)
        except Exception as e:
            print(f"❌ ERROR: Failed to load cash inventory: {e}")
            self.show_message.emit("Error", f"Failed to load cash inventory: {str(e)}")
    
    def load_error_log(self):
        """Loads error log from the database."""
        try:
            print("🔄 Loading error log from database...")
            errors = self.db_manager.get_error_log()
            print(f"✅ Loaded {len(errors)} error log entries")
            self.error_log_loaded.emit(errors)
        except Exception as e:
            print(f"❌ ERROR: Failed to load error log: {e}")
            self.show_message.emit("Error", f"Failed to load error log: {str(e)}")
    
    def refresh_all_data(self):
        """Refreshes all data types."""
        self.load_transactions()
        self.load_cash_inventory()
        self.load_error_log()
