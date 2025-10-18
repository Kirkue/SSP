from PyQt5.QtCore import QObject, pyqtSignal, QTimer

class PinDialogModel(QObject):
    """Model for the PIN Dialog - handles PIN validation logic and state management."""
    
    # Signals for UI updates
    pin_updated = pyqtSignal(str)  # pin_display_text (asterisks)
    status_updated = pyqtSignal(str)  # status_message
    pin_validated = pyqtSignal(bool)  # is_valid
    clear_requested = pyqtSignal()  # request to clear input
    
    def __init__(self):
        super().__init__()
        self.CORRECT_PIN = "1234"
        self.current_pin = ""
        self.max_pin_length = 8
        
    def add_digit(self, digit):
        """Adds a digit to the current PIN if within length limit."""
        if len(self.current_pin) < self.max_pin_length:
            self.current_pin += digit
            self.pin_updated.emit('*' * len(self.current_pin))
    
    def clear_pin(self):
        """Clears the current PIN."""
        self.current_pin = ""
        self.pin_updated.emit('')
        self.status_updated.emit("Enter PIN")
    
    def validate_pin(self):
        """Validates the current PIN against the correct PIN."""
        is_valid = self.current_pin == self.CORRECT_PIN
        self.pin_validated.emit(is_valid)
        
        if not is_valid:
            self.status_updated.emit("Incorrect PIN")
            # Schedule auto-clear after 1 second
            QTimer.singleShot(1000, self.clear_pin)
        
        return is_valid
    
    def get_current_pin(self):
        """Returns the current PIN (for testing purposes)."""
        return self.current_pin
    
    def is_pin_complete(self):
        """Checks if the PIN has reached the maximum length."""
        return len(self.current_pin) >= self.max_pin_length
