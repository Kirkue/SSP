# screens/admin/model.py

from PyQt5.QtCore import QObject, pyqtSignal
from database.db_manager import DatabaseManager
from managers.sms_manager import get_sms_manager

class AdminModel(QObject):
    """Handles the data and business logic for the admin screen."""
    paper_count_changed = pyqtSignal(int, str)  # Emits new count and display color
    coin_count_changed = pyqtSignal(int, int)   # Emits coin_1_count, coin_5_count
    cmyk_levels_changed = pyqtSignal(float, float, float, float)  # Emits cyan, magenta, yellow, black
    show_message = pyqtSignal(str, str)         # Emits message title and text

    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.sms_manager = get_sms_manager()
        self.paper_count = 100
        self.sms_alert_sent = False
        
        # Initialize the modem when the model is created
        self.sms_manager.initialize_modem()

    def load_paper_count(self):
        """Loads the paper count from the database and emits a signal."""
        self.paper_count = self.db_manager.get_setting('paper_count', default=100)
        print(f"AdminModel.load_paper_count: Loaded {self.paper_count} from database")
        color = self._get_color_for_count(self.paper_count)
        self.paper_count_changed.emit(self.paper_count, color)

    def reset_paper_count(self):
        """Resets the paper count to 100."""
        self.paper_count = 100
        self.db_manager.update_setting('paper_count', self.paper_count)
        self.sms_alert_sent = False
        print("Paper count reset to 100, SMS alert flag reset.")
        self.load_paper_count() # Reload to emit signal

    def update_paper_count_from_string(self, count_str: str):
        """Validates and updates the paper count from user input string."""
        try:
            new_count = int(count_str)
            if not (0 <= new_count <= 100):
                self.show_message.emit("Invalid Input", "Paper count must be between 0 and 100.")
                self.load_paper_count() # Revert display to current value
                return

            old_count = self.paper_count
            self.paper_count = new_count
            self.db_manager.update_setting('paper_count', self.paper_count)

            if new_count > old_count and new_count > 10:
                self.sms_alert_sent = False
            
            self.check_low_paper_alert()
            self.load_paper_count() # Reload to emit signal
            print(f"Paper count updated from {old_count} to {new_count} sheets.")

        except ValueError:
            self.show_message.emit("Invalid Input", "Please enter a valid number.")
            self.load_paper_count() # Revert display

    def decrement_paper_count(self, pages_to_print: int) -> bool:
        """Decrements paper count for a print job. Returns True on success."""
        if self.paper_count >= pages_to_print:
            self.paper_count = max(0, self.paper_count - pages_to_print)
            self.db_manager.update_setting('paper_count', self.paper_count)
            self.check_low_paper_alert()
            self.load_paper_count() # Emit signal to update any listening UI
            print(f"Paper count updated to {self.paper_count} sheets.")
            return True
        else:
            print(f"ERROR: Not enough paper. Required: {pages_to_print}, Available: {self.paper_count}")
            return False

    def check_low_paper_alert(self):
        """Checks for low paper and sends an SMS alert if needed."""
        if self.paper_count <= 10 and not self.sms_alert_sent:
            print(f"Low paper detected: {self.paper_count} sheets remaining. Sending alert.")
            message = f"ALERT: Paper is low ({self.paper_count} sheets left). Please refill soon."
            
            # FIX: Use the correct method from sms_manager
            if self.sms_manager.send_custom_alert(message):
                self.sms_alert_sent = True
                print("Low paper SMS sent successfully.")
            else:
                print("Failed to send low paper SMS.")

        elif self.paper_count > 10:
            self.sms_alert_sent = False

    def load_coin_counts(self):
        """Loads the coin counts from the database and emits a signal."""
        try:
            inventory = self.db_manager.get_cash_inventory()
            coin_1_count = 0
            coin_5_count = 0
            
            for item in inventory:
                if item['denomination'] == 1 and item['type'] == 'coin':
                    coin_1_count = item['count']
                elif item['denomination'] == 5 and item['type'] == 'coin':
                    coin_5_count = item['count']
            
            self.coin_count_changed.emit(coin_1_count, coin_5_count)
            print(f"Coin counts loaded: ₱1={coin_1_count}, ₱5={coin_5_count}")
            
        except Exception as e:
            print(f"Error loading coin counts: {e}")
            self.coin_count_changed.emit(0, 0)

    def update_coin_1_count(self, count_str: str):
        """Validates and updates the ₱1 coin count from user input."""
        try:
            new_count = int(count_str)
            if not (0 <= new_count <= 1000):
                self.show_message.emit("Invalid Input", "₱1 coin count must be between 0 and 1000.")
                self.load_coin_counts()
                return

            self.db_manager.update_cash_inventory(1, new_count, 'coin')
            self.load_coin_counts()
            print(f"₱1 coin count updated to {new_count}")

        except ValueError:
            self.show_message.emit("Invalid Input", "Please enter a valid number for ₱1 coins.")
            self.load_coin_counts()

    def update_coin_5_count(self, count_str: str):
        """Validates and updates the ₱5 coin count from user input."""
        try:
            new_count = int(count_str)
            if not (0 <= new_count <= 1000):
                self.show_message.emit("Invalid Input", "₱5 coin count must be between 0 and 1000.")
                self.load_coin_counts()
                return

            self.db_manager.update_cash_inventory(5, new_count, 'coin')
            self.load_coin_counts()
            print(f"₱5 coin count updated to {new_count}")

        except ValueError:
            self.show_message.emit("Invalid Input", "Please enter a valid number for ₱5 coins.")
            self.load_coin_counts()

    def reset_coin_counts(self):
        """Resets both coin counts to default values."""
        self.db_manager.update_cash_inventory(1, 100, 'coin')  # Default 100 ₱1 coins
        self.db_manager.update_cash_inventory(5, 50, 'coin')   # Default 50 ₱5 coins
        self.load_coin_counts()
        print("Coin counts reset to defaults: ₱1=100, ₱5=50")

    def decrement_coins(self, peso_1_needed: int, peso_5_needed: int) -> bool:
        """Decrements coin counts for change dispensing. Returns True on success."""
        try:
            # Get current counts
            inventory = self.db_manager.get_cash_inventory()
            current_1 = 0
            current_5 = 0
            
            for item in inventory:
                if item['denomination'] == 1 and item['type'] == 'coin':
                    current_1 = item['count']
                elif item['denomination'] == 5 and item['type'] == 'coin':
                    current_5 = item['count']
            
            # Check if we have enough coins
            if current_1 < peso_1_needed or current_5 < peso_5_needed:
                print(f"ERROR: Not enough coins. Required: ₱1={peso_1_needed}, ₱5={peso_5_needed}. Available: ₱1={current_1}, ₱5={current_5}")
                return False
            
            # Update counts
            new_1_count = current_1 - peso_1_needed
            new_5_count = current_5 - peso_5_needed
            
            self.db_manager.update_cash_inventory(1, new_1_count, 'coin')
            self.db_manager.update_cash_inventory(5, new_5_count, 'coin')
            
            self.load_coin_counts()
            print(f"Coins dispensed: ₱1={peso_1_needed}, ₱5={peso_5_needed}. Remaining: ₱1={new_1_count}, ₱5={new_5_count}")
            return True
            
        except Exception as e:
            print(f"Error dispensing coins: {e}")
            return False

    def get_coin_counts(self):
        """Returns current coin counts as a tuple (coin_1, coin_5)."""
        try:
            inventory = self.db_manager.get_cash_inventory()
            coin_1_count = 0
            coin_5_count = 0
            
            for item in inventory:
                if item['denomination'] == 1 and item['type'] == 'coin':
                    coin_1_count = item['count']
                elif item['denomination'] == 5 and item['type'] == 'coin':
                    coin_5_count = item['count']
            
            return coin_1_count, coin_5_count
            
        except Exception as e:
            print(f"Error getting coin counts: {e}")
            return 0, 0

    def load_cmyk_levels(self):
        """Loads the CMYK ink levels from the database and emits a signal."""
        try:
            cmyk_data = self.db_manager.get_cmyk_ink_levels()
            if cmyk_data:
                self.cmyk_levels_changed.emit(
                    cmyk_data['cyan'], 
                    cmyk_data['magenta'], 
                    cmyk_data['yellow'], 
                    cmyk_data['black']
                )
                print(f"CMYK levels loaded: C:{cmyk_data['cyan']:.1f}% M:{cmyk_data['magenta']:.1f}% Y:{cmyk_data['yellow']:.1f}% K:{cmyk_data['black']:.1f}%")
            else:
                # No data available, set default values
                self.cmyk_levels_changed.emit(100.0, 100.0, 100.0, 100.0)
                print("No CMYK data found, using default values (100%)")
        except Exception as e:
            print(f"Error loading CMYK levels: {e}")
            self.cmyk_levels_changed.emit(100.0, 100.0, 100.0, 100.0)
    
    def refresh_cmyk_levels(self):
        """Refresh CMYK levels from database (alias for load_cmyk_levels)."""
        self.load_cmyk_levels()

    def update_cmyk_levels(self, cyan: float, magenta: float, yellow: float, black: float):
        """Updates CMYK ink levels in the database."""
        try:
            # Validate ranges
            if not (0.0 <= cyan <= 100.0 and 0.0 <= magenta <= 100.0 and 
                    0.0 <= yellow <= 100.0 and 0.0 <= black <= 100.0):
                self.show_message.emit("Invalid Input", "CMYK values must be between 0.0 and 100.0")
                self.load_cmyk_levels()
                return

            success = self.db_manager.update_cmyk_ink_levels(cyan, magenta, yellow, black)
            if success:
                self.load_cmyk_levels()
                print(f"CMYK levels updated: C:{cyan:.1f}% M:{magenta:.1f}% Y:{yellow:.1f}% K:{black:.1f}%")
            else:
                self.show_message.emit("Database Error", "Failed to update CMYK levels")
                
        except Exception as e:
            print(f"Error updating CMYK levels: {e}")
            self.show_message.emit("Error", f"Failed to update CMYK levels: {e}")

    def reset_cmyk_levels(self):
        """Resets all CMYK ink levels to 100%."""
        try:
            success = self.db_manager.update_cmyk_ink_levels(100.0, 100.0, 100.0, 100.0)
            if success:
                self.load_cmyk_levels()
                print("CMYK levels reset to 100%")
            else:
                self.show_message.emit("Database Error", "Failed to reset CMYK levels")
        except Exception as e:
            print(f"Error resetting CMYK levels: {e}")
            self.show_message.emit("Error", f"Failed to reset CMYK levels: {e}")

    def _get_color_for_count(self, count: int) -> str:
        """Determines the display color based on the paper count."""
        if count <= 20: return "#dc3545"
        if count <= 50: return "#ffc107"
        return "#28a745"