from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from config import get_config
from managers.pin_lockout import PinLockout


class PinDialogModel(QObject):
    """Model for the PIN Dialog - handles PIN validation logic and state management."""

    # Signals for UI updates
    pin_updated = pyqtSignal(str)  # pin_display_text (asterisks)
    status_updated = pyqtSignal(str)  # status_message
    pin_validated = pyqtSignal(bool)  # is_valid
    clear_requested = pyqtSignal()  # request to clear input
    lock_changed = pyqtSignal(bool, int)  # is_locked, seconds_remaining

    def __init__(self, lockout=None):
        super().__init__()
        self.lockout = lockout if lockout is not None else self._default_lockout()
        self.CORRECT_PIN = get_config().admin_pin
        self.current_pin = ""
        self.max_pin_length = 8

    @staticmethod
    def _default_lockout():
        from database.db_manager import DatabaseManager
        from managers.sms_manager import send_operator_alert
        cfg = get_config()

        def alert(message):
            if not cfg.sim_mode:
                send_operator_alert(message)

        return PinLockout(DatabaseManager(), cfg.admin_pin_max_attempts,
                          cfg.admin_pin_lockout_minutes, on_lockout=alert)

    def close(self):
        """Releases the lockout's DB connection and stops further use."""
        self._lock_db_close()

    def _lock_db_close(self):
        db = getattr(self.lockout, 'db', None)
        if db is not None and hasattr(db, 'close'):
            db.close()

    def is_locked(self):
        return self.lockout.is_locked()

    def refresh_lock(self):
        """Emits the current lock state (called on open and every second)."""
        remaining = self.lockout.remaining()
        if remaining > 0:
            self.current_pin = ""
            self.pin_updated.emit('')
        self.lock_changed.emit(remaining > 0, remaining)

    def add_digit(self, digit):
        """Adds a digit to the current PIN if within length limit."""
        if self.is_locked():
            return
        if len(self.current_pin) < self.max_pin_length:
            self.current_pin += digit
            self.pin_updated.emit('*' * len(self.current_pin))

    def clear_pin(self):
        """Clears the current PIN."""
        self.current_pin = ""
        self.pin_updated.emit('')
        if not self.is_locked():
            self.status_updated.emit("Enter PIN")

    def validate_pin(self):
        """Validates the current PIN against the correct PIN."""
        if self.is_locked():
            self.refresh_lock()
            return False
        is_valid = self.current_pin == self.CORRECT_PIN
        if is_valid:
            self.lockout.record_success()
        elif self.lockout.record_failure():
            self.refresh_lock()
            return False
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
