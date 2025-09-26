from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal
from .model import PaymentModel
from .view import PaymentScreenView

class PaymentController(QWidget):
    """Controller for the Payment screen - coordinates between model and view."""
    
    # Signals for external communication
    payment_completed = pyqtSignal(dict)
    go_back_to_viewer = pyqtSignal(dict)
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = PaymentModel(main_app)
        self.view = PaymentScreenView()
        
        # Set the view's layout as this controller's layout
        self.setLayout(self.view.main_layout)
        
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller -> Model ---
        self.view.back_button_clicked.connect(self.model.go_back)
        self.view.payment_mode_toggle_clicked.connect(self._toggle_payment_mode)
        self.view.payment_button_clicked.connect(self._complete_payment)
        self.view.simulation_coin_clicked.connect(self.model.simulate_coin)
        self.view.simulation_bill_clicked.connect(self.model.simulate_bill)
        
        # --- Model -> Controller -> View ---
        self.model.payment_data_updated.connect(self.view.update_payment_data)
        self.model.payment_status_updated.connect(self.view.update_payment_status)
        self.model.amount_received_updated.connect(self.view.update_amount_received)
        self.model.change_updated.connect(self.view.update_change_display)
        self.model.payment_button_enabled.connect(self.view.set_payment_button_enabled)
        self.model.payment_mode_changed.connect(self.view.set_payment_mode_button_state)
        self.model.payment_completed.connect(self._handle_payment_completed)
        self.model.go_back_requested.connect(self._go_back)
    
    def _toggle_payment_mode(self):
        """Toggles between enable and disable payment mode."""
        if self.model.payment_ready:
            self.model.disable_payment_mode()
        else:
            self.model.enable_payment_mode()
    
    def _complete_payment(self):
        """Handles payment completion."""
        success, message = self.model.complete_payment(self.main_app)
        if not success:
            QMessageBox.warning(self, "Payment Error", message)
    
    def _handle_payment_completed(self, payment_info):
        """Handles payment completion signal from model."""
        if 'navigate_to' in payment_info:
            # This is a navigation signal from change dispensing
            if payment_info['navigate_to'] == 'thank_you':
                self.main_app.show_screen('thank_you')
        else:
            # This is actual payment completion
            self.payment_completed.emit(payment_info)
            self.view.set_buttons_enabled(False, False, False)
    
    def _go_back(self):
        """Handles go back request from model."""
        if hasattr(self.main_app, 'show_screen'):
            self.main_app.show_screen('printing_options')
    
    def set_payment_data(self, payment_data):
        """Sets payment data in the model."""
        self.model.set_payment_data(payment_data)
        self.view.set_buttons_enabled(True, True, False)
    
    def on_enter(self):
        """Called when the payment screen is shown."""
        self.model.on_enter()
        self.view.set_buttons_enabled(True, True, False)
    
    def on_leave(self):
        """Called when leaving the payment screen."""
        self.model.on_leave()
    
    def go_back(self):
        """Public method to go back to print options screen."""
        self.model.go_back()
