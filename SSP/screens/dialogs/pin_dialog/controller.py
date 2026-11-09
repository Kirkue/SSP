from PyQt5.QtCore import QTimer

from .model import PinDialogModel
from .view import PinDialogView


class PinDialogController(PinDialogView):
    """Controller for the PIN Dialog - coordinates between model and view."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = PinDialogModel()
        self._connect_signals()

        # Live countdown while locked; the deadline itself is wall-clock state
        # in the model, so this timer only drives the display.
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(1000)
        self._lock_timer.timeout.connect(self.model.refresh_lock)
        self._lock_timer.start()
        self.model.refresh_lock()
        self.finished.connect(self._lock_timer.stop)
        self.finished.connect(self.model.close)

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller -> Model ---
        self.number_clicked.connect(self.model.add_digit)
        self.clear_clicked.connect(self.model.clear_pin)
        self.enter_clicked.connect(self._validate_pin)

        # --- Model -> Controller -> View ---
        self.model.pin_updated.connect(self.update_pin_display)
        self.model.status_updated.connect(self.update_status)
        self.model.lock_changed.connect(self.set_locked)
        self.model.pin_validated.connect(self._handle_pin_validation)

    def _validate_pin(self):
        """Handles PIN validation."""
        is_valid = self.model.validate_pin()
        if is_valid:
            self.accept()  # Close dialog with success

    def _handle_pin_validation(self, is_valid):
        """Handles the result of PIN validation."""
        if is_valid:
            self.accept()  # Close dialog with success
