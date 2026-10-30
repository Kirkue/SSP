from PyQt5.QtWidgets import QWidget, QGridLayout, QDialog

from managers.timeout_manager import TimeoutPolicy
from screens.dialogs.pin_dialog import PinDialogController as PinDialog
from .model import HomepageModel
from .view import HomepageScreenView


class HomepageController(QWidget):
    """Manages the Landing (upload method selection) screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = HomepageModel()
        self.view = HomepageScreenView()
        self._pin_dialog_open = False

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""

        self.view.method_card_clicked.connect(self._handle_method_selected)

        self.model.method_selected.connect(self._route_method)

        self.view.voucher_balance_clicked.connect(self._check_voucher_balance)
        self.view.admin_button_clicked.connect(self._go_to_admin)

    def _handle_method_selected(self, method_key):
        """Passes the selected method to the model."""
        self.model.select_method(method_key)

    def _route_method(self, method_key):
        """Routes to the correct screen based on the selected method."""
        if method_key == 'usb':
            self.main_app.show_screen('usb')
        elif method_key == 'wifi':
            self.main_app.show_screen('wifi')
        elif method_key == 'email':
            self.main_app.show_screen('email')
        elif method_key == 'scanner':
            # Scanner backend is still a stub (project_objectives.txt module 8).
            self.main_app.show_screen('scanner')
        else:
            print(f"Landing screen: Unknown method selected: {method_key}")

    def _check_voucher_balance(self):
        """A popup over this screen: it doesn't start a print job or leave the homepage."""
        self.main_app.open_voucher_balance()

    def _go_to_admin(self):
        """Opens the PIN dialog (same as the idle screen) and goes to admin if correct."""
        # The dialog runs its own event loop, so the timeout must not expire behind it.
        self._pin_dialog_open = True
        try:
            accepted = PinDialog(self).exec_() == QDialog.Accepted
        finally:
            self._pin_dialog_open = False
        if accepted:
            self.main_app.show_screen('admin')

    def show_qr_message(self, message):
        """A message about a QR read (from main_app)."""
        self.view.show_status(message, is_error=True)

    def _go_back(self):
        """Navigates back to the idle screen."""
        self.main_app.show_screen('idle')

    # --- Public API for main_app ---

    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Homepage screen entered")
        self.view.show_status("")
        self.view.set_change_low(self.model.is_change_low())

    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Homepage screen leaving")

    def timeout_policy(self):
        return TimeoutPolicy(seconds=60, action=self._on_timeout, busy=lambda: self._pin_dialog_open)

    def _on_timeout(self):
        """Nobody has chosen a way to upload yet: back to idle."""
        print("Homepage screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
