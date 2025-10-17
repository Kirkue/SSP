from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
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
        
        # Setup timeout timer (1 minute = 60000ms)
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        
        # Inline suggestion only (no popup controller)
        
        # Set the view's layout as this controller's layout
        self.setLayout(self.view.main_layout)
        
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller -> Model ---
        self.view.back_button_clicked.connect(self.model.go_back)
        # popup removed
        self.view.simulation_coin_clicked.connect(self.model.simulate_coin)
        self.view.simulation_bill_clicked.connect(self.model.simulate_bill)
        
        # Reset timeout on user interaction
        self.view.back_button_clicked.connect(self._reset_timeout)
        self.view.simulation_coin_clicked.connect(self._reset_timeout)
        self.view.simulation_bill_clicked.connect(self._reset_timeout)
        
        # --- Model -> Controller -> View ---
        self.model.payment_data_updated.connect(self.view.update_payment_data)
        self.model.payment_status_updated.connect(self.view.update_payment_status)
        self.model.amount_received_updated.connect(self.view.update_amount_received)
        self.model.change_updated.connect(self.view.update_change_display)
        self.model.suggestion_updated.connect(self.view.update_inline_suggestion)
        self.model.payment_completed.connect(self._handle_payment_completed)
        self.model.go_back_requested.connect(self._go_back)
    
    def on_enter(self):
        """Called when entering the payment screen - automatically enable payment."""
        print("Payment screen entered - automatically enabling payment")
        # Reset payment state for new transactions
        self.model.reset_payment_state()
        # Enable payment mode
        self.model.enable_payment_mode()
    
    def on_leave(self):
        """Called when leaving the payment screen - automatically disable payment."""
        print("Payment screen leaving - automatically disabling payment")
        self.model.disable_payment_mode()
    
    
    def _handle_payment_completed(self, payment_info):
        """Handles payment completion signal from model."""
        if 'navigate_to' in payment_info:
            # This is a navigation signal from change dispensing
            if payment_info['navigate_to'] == 'thank_you':
                self.main_app.show_screen('thank_you')
        else:
            # This is actual payment completion
            self.payment_completed.emit(payment_info)
            self.view.set_buttons_enabled(False)
    
    def _go_back(self):
        """Handles go back request from model."""
        if hasattr(self.main_app, 'show_screen'):
            self.main_app.show_screen('printing_options')
    
    def set_payment_data(self, payment_data):
        """Sets payment data in the model."""
        self.model.set_payment_data(payment_data)
        self.view.set_buttons_enabled(True)
    
    def on_enter(self):
        """Called when the payment screen is shown."""
        self.model.on_enter()
        self.view.set_buttons_enabled(True)
    
    def on_leave(self):
        """Called when leaving the payment screen."""
        self.model.on_leave()
    
    def go_back(self):
        """Public method to go back to print options screen."""
        self.model.go_back()
    
    # popup removed
    
    def _on_suggestion_selected(self, amount):
        """Handle when user selects a payment suggestion."""
        try:
            # Set the suggested amount in the model
            self.model.amount_received = amount
            self.model.amount_received_updated.emit(amount)
            self.model._update_payment_status()
            
            print(f"Payment suggestion selected: ₱{amount:.2f}")
            
        except Exception as e:
            print(f"Error handling suggestion selection: {e}")
    
    def _on_exact_payment_requested(self):
        """Handle when user requests exact payment."""
        try:
            # Set exact amount
            self.model.amount_received = self.model.total_cost
            self.model.amount_received_updated.emit(self.model.total_cost)
            self.model._update_payment_status()
            
            print(f"Exact payment requested: ₱{self.model.total_cost:.2f}")
            
        except Exception as e:
            print(f"Error handling exact payment request: {e}")

    # When model recomputes the best suggestion, reflect it in the view via existing status signal
    # PaymentModel already emits payment_status_updated; hook that to update label too
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        # Start timeout timer (1 minute)
        self.timeout_timer.start(60000)
        print("⏰ Payment screen timeout started (1 minute)")
        
        # Automatically enable payment when entering the screen
        self.model.enable_payment_mode()
        print("✅ Payment automatically enabled on screen entry")
    
    def on_leave(self):
        """Called by main_app when leaving this screen."""
        # Stop timeout timer
        self.timeout_timer.stop()
    
    def _on_timeout(self):
        """Handle timeout - return to idle screen."""
        print("⏰ Payment screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
    
    def _reset_timeout(self):
        """Reset the timeout timer (call on user activity)."""
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        print("⏰ Payment screen timeout reset")
