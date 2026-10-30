from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import pyqtSignal
from .model import PaymentModel
from managers.timeout_manager import TimeoutPolicy
from managers.voucher_manager import CODE_ALPHABET
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
        self.view = PaymentScreenView(voucher_keys=CODE_ALPHABET)

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
        self.view.voucher_code_entered.connect(self.apply_voucher_code)

        # A coin or bill is activity too, though it isn't a tap (a bill takes seconds to validate)
        self.model.amount_received_updated.connect(lambda _amount: self.main_app.note_activity())

        # --- Model -> Controller -> View ---
        self.model.payment_data_updated.connect(self.view.update_payment_data)
        self.model.payment_status_updated.connect(self.view.update_payment_status)
        self.model.amount_received_updated.connect(self.view.update_amount_received)
        self.model.change_updated.connect(self.view.update_change_display)
        self.model.suggestion_updated.connect(self.view.update_inline_suggestion)
        self.model.vouchers_updated.connect(self.view.update_vouchers)
        self.model.voucher_message.connect(self.view.show_voucher_message)
        self.model.payment_completed.connect(self._handle_payment_completed)
        self.model.go_back_requested.connect(self._go_back)
        self.model.payment_locked.connect(lambda locked: self.view.set_buttons_enabled(not locked))

    def apply_voucher_code(self, raw_code):
        """Apply a Voucher from the "Use a voucher" entry or a QR read. Takes a
        typed code or a 'V1:<code>' payload, so a QR read can be passed straight in."""
        return self.model.apply_voucher(raw_code)

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
            # A digital-only scan has no print options to go back to.
            self.main_app.show_screen(
                'printing_options' if self.model.is_print_job() else 'scan_destination')

    def set_payment_data(self, payment_data):
        """Sets payment data in the model."""
        self.model.set_payment_data(payment_data)
        self.view.set_buttons_enabled(True)

    def on_enter(self):
        """Called when the payment screen is shown."""
        print("*** PAYMENT CONTROLLER ON_ENTER METHOD CALLED ***")
        print("=== PAYMENT CONTROLLER ON_ENTER START ===")
        print("DEBUG: Payment controller on_enter() called")
        print(f"DEBUG: Controller type: {type(self)}")
        print(f"DEBUG: Model type: {type(self.model)}")
        print(f"DEBUG: View type: {type(self.view)}")

        self.view.reset_voucher_entry()
        print("DEBUG: About to call model.on_enter()")
        try:
            self.model.on_enter()
            print("DEBUG: model.on_enter() completed")
        except Exception as e:
            print(f"DEBUG: model.on_enter() failed with error: {e}")
        self.view.set_buttons_enabled(True)
        print("DEBUG: Payment controller on_enter() completed")
        print("=== PAYMENT CONTROLLER ON_ENTER END ===")

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

            print(f"Payment suggestion selected: P{amount:.2f}")

        except Exception as e:
            print(f"Error handling suggestion selection: {e}")

    def _on_exact_payment_requested(self):
        """Handle when user requests exact payment."""
        try:
            # Set exact amount
            self.model.amount_received = self.model.total_cost
            self.model.amount_received_updated.emit(self.model.total_cost)
            self.model._update_payment_status()

            print(f"Exact payment requested: P{self.model.total_cost:.2f}")

        except Exception as e:
            print(f"Error handling exact payment request: {e}")

    # When model recomputes the best suggestion, reflect it in the view via existing status signal
    # PaymentModel already emits payment_status_updated; hook that to update label too

    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("*** PAYMENT CONTROLLER ON_LEAVE METHOD CALLED ***")
        # Disable payment pins
        self.model.on_leave()
        print("*** PAYMENT CONTROLLER ON_LEAVE COMPLETED ***")

    def timeout_policy(self):
        # Never while the payment completes or change is coming out: leaving then would
        # stop the hoppers mid-payout (PaymentModel.is_busy).
        return TimeoutPolicy(seconds=60, action=self._on_timeout, busy=self.model.is_busy,
                             warning_message=self._timeout_warning_message)

    def _timeout_warning_message(self):
        """What the "Still there?" prompt says about cash already inserted (Carried Credit)."""
        amount = self.model.amount_received
        if amount > 0:
            return f"Your ₱{amount:g} will be saved as a voucher."
        return ""

    def _on_timeout(self):
        """The customer walked away mid-flow: back to the homepage. Cash already in becomes a
        Voucher (show_screen's carried-credit redirect), and their files are cleared."""
        if self.model.is_busy():
            return   # the policy already holds the timeout off; belt and braces
        print("TIMEOUT: Payment screen timeout - returning to homepage")
        # Properly clean up payment screen before navigating away
        self.on_leave()
        # Additional safety: manually disable acceptors as backup
        self._manual_disable_acceptors()
        self.main_app.end_session()
        self.main_app.show_screen('homepage')

    def _manual_disable_acceptors(self):
        """Manually disable acceptors as a safety backup."""
        print("PAYMENT: Manually disabling acceptors as safety backup...")

        try:
            import pigpio

            # Create a temporary GPIO connection for manual control
            pi = pigpio.pi()
            if not pi.connected:
                print("PAYMENT: Could not connect to pigpio daemon for manual disable")
                return

            # GPIO pin definitions
            COIN_INHIBIT_PIN = 22  # Coin acceptor inhibit pin
            BILL_INHIBIT_PIN = 23   # Bill acceptor inhibit pin

            # Disable coin acceptor (HIGH = enabled, LOW = disabled)
            pi.set_mode(COIN_INHIBIT_PIN, pigpio.OUTPUT)
            pi.write(COIN_INHIBIT_PIN, 0)  # LOW = disabled
            print("PAYMENT: Coin acceptor manually disabled")

            # Disable bill acceptor (LOW = enabled, HIGH = disabled)
            pi.set_mode(BILL_INHIBIT_PIN, pigpio.OUTPUT)
            pi.write(BILL_INHIBIT_PIN, 1)  # HIGH = disabled
            print("PAYMENT: Bill acceptor manually disabled")

            # Small delay to ensure state change
            import time
            time.sleep(0.1)

            # Clean up the temporary connection
            pi.stop()
            print("PAYMENT: Acceptors manually disabled successfully")

        except ImportError:
            print("PAYMENT: GPIO not available - acceptors disabled (simulation mode)")
        except Exception as e:
            print(f"PAYMENT: Error manually disabling acceptors: {e}")
            # Try to clean up even if there was an error
            try:
                if 'pi' in locals():
                    pi.stop()
            except Exception:
                pass
