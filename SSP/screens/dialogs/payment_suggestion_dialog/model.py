# screens/dialogs/payment_suggestion_dialog/model.py

from PyQt5.QtCore import QObject


class PaymentSuggestionModel(QObject):
    """Model for the payment suggestion dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def get_suggestion_summary(self, suggestions):
        """Get a summary of payment suggestions."""
        if not suggestions:
            return "No payment suggestions available"
        
        exact_payments = [s for s in suggestions if s['change'] == 0]
        change_payments = [s for s in suggestions if s['change'] > 0]
        
        summary = f"Found {len(suggestions)} payment options: "
        if exact_payments:
            summary += f"{len(exact_payments)} exact payment(s), "
        if change_payments:
            summary += f"{len(change_payments)} with change"
        
        return summary
