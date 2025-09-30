# screens/dialogs/payment_suggestion_dialog/controller.py

from PyQt5.QtCore import QObject, pyqtSignal
from .view import PaymentSuggestionDialog


class PaymentSuggestionController(QObject):
    """Controller for the payment suggestion dialog."""
    
    suggestion_selected = pyqtSignal(float)  # Forward signal from dialog
    exact_payment_requested = pyqtSignal()  # Forward signal from dialog
    dialog_closed = pyqtSignal()            # Emitted when dialog is closed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dialog = None
        
    def show_dialog(self, total_cost, suggestions, status_message):
        """Show the payment suggestion dialog."""
        self.dialog = PaymentSuggestionDialog(
            total_cost, suggestions, status_message, self.parent()
        )
        
        # Connect dialog signals
        self.dialog.suggestion_selected.connect(self.suggestion_selected.emit)
        self.dialog.exact_payment_requested.connect(self.exact_payment_requested.emit)
        self.dialog.finished.connect(self._on_dialog_finished)
        
        # Show dialog
        self.dialog.show()
        
    def _on_dialog_finished(self, result):
        """Handle dialog completion."""
        self.dialog_closed.emit()
        self.dialog = None
