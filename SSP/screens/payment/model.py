import os
import shutil
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, List, Dict, Optional
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from managers.hopper_manager import ChangeDispenser, DispenseThread
from managers.payment_algorithm_manager import PaymentAlgorithmManager
from database.db_manager import DatabaseManager
from utils.error_logger import log_error

try:
    import pigpio
except ImportError:
    pigpio = None  # GPIOPaymentThread falls back to mock GPIO when pigpio is missing

from managers.persistent_gpio import get_persistent_gpio, PIGPIO_AVAILABLE as PAYMENT_GPIO_AVAILABLE
import uuid
from managers.voucher_manager import MSG_UNGIVEN_CHANGE, IssuedVoucher, LookupStatus, VoucherManager, normalize_code
from managers.sms_manager import send_operator_alert
from managers.adapters.scan_adapter import ScanAdapter
from managers.session_manager import SessionManager
from managers.print_refund import record_digital_refund, record_print_success
from config import get_config


def _document_name(pdf_data):
    """The customer-facing name of the document being paid for: the original
    filename file_browser shows, not the stored <uuid>.pdf copy's name."""
    return pdf_data.get('filename') or os.path.basename(pdf_data.get('path') or '')


def measure_shortfall(result, change_owed):
    """Change owed minus change actually dispensed, whole pesos. The failure
    paths (no pigpio, hopper init, dispenser None) return no actual_change,
    so they count as nothing dispensed: the whole change becomes a voucher."""
    if isinstance(result, dict) and 'actual_change' in result:
        expected = result.get('expected_change', change_owed)
        actual = result['actual_change']
    else:
        expected, actual = change_owed, 0
    return max(0, int(round(expected - actual)))


class ShortfallCause(Enum):
    """Why change went short. Only HOPPER_FAILURE alerts the operator."""
    PREDICTED = 'predicted'            # the hoppers didn't hold enough coins
    HOPPER_FAILURE = 'hopper_failure'  # a hopper stopped early or couldn't be driven


@dataclass
class ShortfallOutcome:
    """What one payment's change came to. PaymentModel is reused for every
    customer, so it swaps in a fresh ShortfallOutcome() instead of resetting
    each field by hand."""
    shortfall: int = 0
    cause: Optional[ShortfallCause] = None
    voucher: Optional[IssuedVoucher] = None  # holds the raw code until the voucher screen takes it
    voucher_failed: bool = False


@dataclass
class AppliedVoucher:
    """A Voucher the customer has Applied on the payment screen. Its value is
    only taken off the Voucher when the payment completes (complete_payment),
    so cancelling or timing out leaves every Voucher untouched."""
    code: str        # canonical code: needed to Apply it, cleared with the payment
    amount: int      # pesos this Voucher pays toward the job
    remaining: int   # what will be left on it afterwards

    @property
    def label(self) -> str:
        # Only the last 4 characters, so the full code isn't left on screen.
        return f"Voucher \u2022\u2022\u2022\u2022-{self.code[-4:]}"


@dataclass
class CarriedCredit:
    """Cash a customer put in without completing the payment, held while they are on
    print options (e.g. after Back to change the page count) and counted again when
    payment reopens. Anywhere else, it becomes a Voucher (redirect_for_carried_credit)."""
    amount: int
    cash: Dict[int, int]  # denomination -> count, for cash inventory
    payment_data: dict    # the job it was put in for, for the cancelled transaction row
    total_cost: float


# Screens a customer can be on while their Carried Credit is kept. Navigating
# anywhere else abandons the payment.
CREDIT_KEPT_ON = {'payment', 'printing_options', 'voucher'}


def redirect_for_carried_credit(main_app, screen_name):
    """Called by show_screen() after the current screen's on_leave(). If the customer
    is leaving an unfinished payment with cash in, issue a Voucher for it and show
    the voucher screen first (it continues to screen_name). Returns the screen to show."""
    if screen_name in CREDIT_KEPT_ON:
        return screen_name
    model = main_app.payment_screen.model
    if model.issue_voucher_for_carried_credit(continue_to=screen_name):
        return 'voucher'
    return screen_name


def shortfall_cause(result, shortfall):
    """The ShortfallCause for a dispense result, or None if there was no Shortfall."""
    if shortfall <= 0:
        return None
    if isinstance(result, dict) and 'actual_change' in result and not result.get('stopped_early'):
        return ShortfallCause.PREDICTED
    return ShortfallCause.HOPPER_FAILURE


class GPIOPaymentThread(QThread):
    """Thread for handling GPIO payment input (coins and bills)."""
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)
    enable_acceptor = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.running = True
        self.pi = None
        self.gpio_available = PAYMENT_GPIO_AVAILABLE
        if self.gpio_available:
            self.setup_gpio()
        else:
            self.setup_mock_gpio()

        self.coin_pulse_count = 0
        self.coin_last_pulse_time = time.time()
        self.bill_pulse_count = 0
        self.bill_last_pulse_time = time.time()
        self.COIN_TIMEOUT = 0.5    # seconds without pulses = end of coin
        self.PULSE_TIMEOUT = 0.5   # Time to wait for additional bill pulses
        self.DEBOUNCE_TIME = 0.1   # Minimum time between pulses

        # Print-related attributes
        self.print_file_path = None

        # Payment tracking attributes
        self.cash_received = {}
        self.change_dispensed = {}
        self.selected_pages = None
        self.copies = 1
        self.color_mode = "Color"

    def setup_gpio(self):
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise Exception("Could not connect to pigpio daemon")
            self.COIN_PIN, self.BILL_PIN, self.INHIBIT_PIN, self.COIN_INHIBIT_PIN = 17, 18, 23, 22

            # Setup coin acceptor GPIO
            self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
            self.pi.callback(self.COIN_PIN, pigpio.FALLING_EDGE, self.coin_pulse_detected)

            # Setup coin acceptor inhibit pin (pin 22)
            self.pi.set_mode(self.COIN_INHIBIT_PIN, pigpio.OUTPUT)
            self.set_coin_acceptor_state(False)  # Start disabled (pin 22 = 0)

            # Setup bill acceptor GPIO
            self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
            self.pi.set_mode(self.INHIBIT_PIN, pigpio.OUTPUT)
            self.set_acceptor_state(False)  # Start disabled
            self.pi.callback(self.BILL_PIN, pigpio.FALLING_EDGE, self.bill_pulse_detected)

            self.payment_status.emit("Payment system ready - Coin and bill acceptors disabled")
        except Exception as e:
            self.payment_status.emit(f"GPIO Error: {str(e)}")
            self.gpio_available = False

    def setup_mock_gpio(self):
        self.payment_status.emit("GPIO not available - Payment system running in simulation mode")

    def set_acceptor_state(self, enable):
        if self.gpio_available and self.pi:
            self.pi.write(self.INHIBIT_PIN, 0 if enable else 1)  # LOW = enabled, HIGH = disabled
            print(f"Bill acceptor {'enabled' if enable else 'disabled'}")
        else:
            self.payment_status.emit(f"Bill acceptor {'enabled' if enable else 'disabled'} (simulation mode)")

    def set_coin_acceptor_state(self, enable):
        if self.gpio_available and self.pi:
            self.pi.write(self.COIN_INHIBIT_PIN, 1 if enable else 0)  # HIGH = enabled, LOW = disabled
            print(f"Coin acceptor {'enabled' if enable else 'disabled'}")
        else:
            self.payment_status.emit(f"Coin acceptor {'enabled' if enable else 'disabled'} (simulation mode)")

    def coin_pulse_detected(self, gpio, level, tick):
        current_time = time.time()
        if current_time - self.coin_last_pulse_time > self.DEBOUNCE_TIME:
            self.coin_pulse_count += 1
            self.coin_last_pulse_time = current_time

    def bill_pulse_detected(self, gpio, level, tick):
        current_time = time.time()
        if current_time - self.bill_last_pulse_time > self.DEBOUNCE_TIME:
            self.bill_pulse_count += 1
            self.bill_last_pulse_time = current_time

    def get_coin_value(self, pulses):
        if pulses == 1:
            return 1
        elif 5 <= pulses <= 7:
            return 5
        elif 10 <= pulses <= 12:
            return 10
        elif 18 <= pulses <= 21:
            return 20
        return 0

    def get_bill_value(self, pulses):
        if pulses == 2:
            return 20
        elif pulses == 5:
            return 50
        elif pulses == 10:
            return 100
        elif pulses == 50:
            return 500
        return 0

    def run(self):
        while self.running:
            now = time.time()
            if self.gpio_available:
                if self.coin_pulse_count > 0 and (now - self.coin_last_pulse_time > self.COIN_TIMEOUT):
                    coin_value = self.get_coin_value(self.coin_pulse_count)
                    if coin_value > 0:
                        self.coin_inserted.emit(coin_value)
                    self.coin_pulse_count = 0
                if self.bill_pulse_count > 0 and (now - self.bill_last_pulse_time > self.PULSE_TIMEOUT):
                    bill_value = self.get_bill_value(self.bill_pulse_count)
                    if bill_value > 0:
                        self.bill_inserted.emit(bill_value)
                    self.bill_pulse_count = 0
            time.sleep(0.05)

    def stop(self):
        """Stop the GPIO thread safely."""
        print("Stopping GPIO payment thread...")
        self.running = False

        # Give the thread a moment to finish its current iteration
        if self.isRunning():
            self.wait(1000)  # Wait up to 1 second for graceful shutdown

        if self.gpio_available and self.pi:
            try:
                self.set_acceptor_state(False)
                # Add a small delay to ensure the acceptor is properly disabled
                import time
                time.sleep(0.1)
                self.pi.stop()
            except Exception as e:
                print(f"Error stopping GPIO: {e}")
            finally:
                self.pi = None


class PaymentModel(QObject):
    """Model for the Payment screen - handles payment logic, GPIO, and change dispensing."""

    # Signals for UI updates
    payment_data_updated = pyqtSignal(dict)  # payment_data
    payment_status_updated = pyqtSignal(str)  # status_message
    suggestion_updated = pyqtSignal(str)      # inline best payment suggestion
    amount_received_updated = pyqtSignal(float)  # amount_received
    change_updated = pyqtSignal(float, str)  # change_amount, change_text
    payment_completed = pyqtSignal(dict)  # payment_info
    go_back_requested = pyqtSignal()  # request to go back
    payment_button_enabled = pyqtSignal(bool)  # enable/disable payment button
    payment_mode_changed = pyqtSignal(bool)  # payment mode enabled/disabled
    vouchers_updated = pyqtSignal(list)       # [AppliedVoucher], in the order Applied
    voucher_message = pyqtSignal(str, bool)   # message, is_error
    payment_locked = pyqtSignal(bool)         # True from auto-complete until change is out

    def __init__(self, main_app=None):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.payment_algorithm = PaymentAlgorithmManager(self.db_manager)
        self.main_app = main_app
        self.total_cost = 0
        self.amount_received = 0
        self.payment_data = None
        self.cash_received = {}
        self.payment_processing = False
        self.payment_ready = False
        self.gpio_thread = None
        self.dispense_thread = None
        self.change_dispenser = ChangeDispenser()
        self.best_payment_suggestion = None  # {'amount', 'change', 'reason'}
        self.payment_ref = None
        self.outcome = ShortfallOutcome()
        self.change_owed = 0
        self.change_dispensed = {}
        self.applied_vouchers = []
        self.carried_credit = None
        self._cash_committed = False  # True once complete_payment has taken the cash
        self.digital_session = None   # paid-for digital copy's session, shown on scan_result
        self.digital_refund = None    # ('issued', Voucher) / ('failed', fee) if it couldn't be made

    def is_print_job(self):
        """False for a digital-only scan: just the fee, nothing to print."""
        return bool(self.payment_data.get('print_job', True)) if self.payment_data else True

    def digital_fee(self):
        return int((self.payment_data or {}).get('digital_copy', {}).get('fee', 0))

    @property
    def voucher_total(self):
        return sum(v.amount for v in self.applied_vouchers)

    @property
    def amount_owed(self):
        """What's still to pay after cash and Applied Vouchers."""
        return max(0, self.total_cost - self.amount_received - self.voucher_total)

    def apply_voucher(self, raw_code):
        """The customer entered a Voucher code (typed, or a 'V1:<code>' payload).
        Checks it now so they see its value straight away, but only takes the
        value off the Voucher in complete_payment. Vouchers count in the order
        they're entered, so at most the last one used is partly used."""
        if not self.payment_ready or getattr(self, '_payment_completing', False):
            return False
        owed = self.amount_owed
        if owed <= 0:
            return False

        code = normalize_code(raw_code)
        if code and any(v.code == code for v in self.applied_vouchers):
            self.voucher_message.emit("You've already applied that voucher", True)
            return False

        lookup = VoucherManager(self.db_manager).balance(raw_code)
        if not lookup.success:
            self.voucher_message.emit(lookup.message, True)
            return False

        take = min(lookup.remaining, int(owed))
        voucher = AppliedVoucher(code=code, amount=take, remaining=lookup.remaining - take)
        self.applied_vouchers.append(voucher)
        self.vouchers_updated.emit(list(self.applied_vouchers))
        self.voucher_message.emit(
            f"Voucher applied: P{take} off. P{voucher.remaining} left on this voucher.", False)
        self._update_payment_status()
        return True

    def _clear_vouchers(self):
        self.applied_vouchers = []
        self.vouchers_updated.emit([])

    def _issue_shortfall_voucher(self, result, change_owed):
        shortfall = measure_shortfall(result, change_owed)
        outcome = self.outcome = ShortfallOutcome(shortfall, shortfall_cause(result, shortfall))
        if shortfall > 0 and self.db_manager.get_setting('vouchers_enabled', 1):
            try:
                outcome.voucher = VoucherManager(self.db_manager).issue(
                    shortfall, payment_ref=self.payment_ref)
            except Exception as e:
                print(f"CRITICAL: could not issue voucher for P{shortfall}: {e}")
                outcome.voucher_failed = True
                try:
                    log_error("Voucher Issue Failed",
                              f"Could not issue a P{shortfall} voucher (payment_ref={self.payment_ref}): {e}",
                              "payment_model")
                except Exception:
                    pass
        td = getattr(self, 'transaction_data', None)
        if td is not None:
            td['change_dispensed'] = change_owed - shortfall
            td['voucher_issued'] = outcome.voucher.value if outcome.voucher else 0
        self._alert_operator_about_shortfall()
        return outcome.voucher

    def _alert_operator_about_shortfall(self):
        """SMS the operator when a hopper failed or a Voucher couldn't be saved.
        A predicted Shortfall (hoppers simply low) needs no alert. Never
        includes the Voucher code."""
        outcome = self.outcome
        shortfall = outcome.shortfall
        hopper = outcome.cause is ShortfallCause.HOPPER_FAILURE
        ref = (self.payment_ref or "")[:8]
        if outcome.voucher_failed:
            message = (f"Kiosk could not save a P{shortfall} change voucher"
                       f"{' after a hopper failure' if hopper else ''}. "
                       f"Customer was told to see the attendant. Ref {ref}")
        elif hopper:
            issued = "voucher issued" if outcome.voucher else "no voucher issued (vouchers off)"
            message = f"Hopper failure: P{shortfall} change not dispensed, {issued}. Check the hoppers. Ref {ref}"
        else:
            return
        try:
            send_operator_alert(message)
        except Exception as e:
            print(f"WARNING: could not send operator alert: {e}")

    def set_payment_data(self, payment_data):
        """Sets the payment data and initializes payment state."""
        self.payment_data = payment_data
        self.total_cost = payment_data['total_cost']
        self.amount_received = 0
        self.cash_received = {}
        self.payment_ready = False
        self.digital_session = None
        self.digital_refund = None
        self._clear_vouchers()

        # Extract print-related attributes for later use
        if 'pdf_data' in payment_data and 'path' in payment_data['pdf_data']:
            self.print_file_path = payment_data['pdf_data']['path']
        if 'selected_pages' in payment_data:
            self.selected_pages = payment_data['selected_pages']
        if 'copies' in payment_data:
            self.copies = payment_data['copies']
        if 'color_mode' in payment_data:
            self.color_mode = payment_data['color_mode']

        print(f"DEBUG: Print attributes set - file: {self.print_file_path}, pages: {self.selected_pages}, copies: {self.copies}, mode: {self.color_mode}")

        # Compute best payment suggestion inline based on current coin inventory
        try:
            best = self.payment_algorithm.find_best_payment_amount(self.total_cost)
            self.best_payment_suggestion = best
            # Notify UI to show suggestion inline
            self.suggestion_updated.emit(self._format_best_payment_status())
        except Exception as e:
            print(f"Error computing best payment suggestion: {e}")

        # Prepare summary data for UI
        analysis = payment_data.get('analysis', {})
        pricing_info = analysis.get('pricing', {})
        b_count = pricing_info.get('black_pages_count', 0)
        c_count = pricing_info.get('color_pages_count', 0)
        doc_name = _document_name(payment_data['pdf_data'])

        summary_data = {
            'total_cost': self.total_cost,
            'document_name': doc_name,
            'copies': payment_data['copies'],
            'color_mode': payment_data['color_mode'],
            'black_pages': b_count,
            'color_pages': c_count,
            'print_job': self.is_print_job(),
            'digital_fee': self.digital_fee(),
        }

        self.payment_data_updated.emit(summary_data)
        self.payment_status_updated.emit("Click 'Enable Payment' to begin")

    def setup_gpio(self):
        """Setup persistent GPIO for payment processing."""
        print("DEBUG: setup_gpio() method called")
        # Use persistent GPIO service instead of creating new thread
        print("DEBUG: About to call get_persistent_gpio()")
        self.persistent_gpio = get_persistent_gpio()
        print(f"DEBUG: Persistent GPIO obtained: {self.persistent_gpio}")
        print(f"DEBUG: Persistent GPIO enabled: {getattr(self.persistent_gpio, 'enabled', 'N/A')}")
        print(f"DEBUG: Persistent GPIO available: {getattr(self.persistent_gpio, 'gpio_available', 'N/A')}")

        # The GPIO service outlives this screen and setup_gpio() runs on every on_enter(),
        # so connect only once: each extra connection credited every coin/bill again.
        if getattr(self, '_connected_gpio', None) is not self.persistent_gpio:
            self.persistent_gpio.coin_inserted.connect(self.on_coin_inserted)
            self.persistent_gpio.bill_inserted.connect(self.on_bill_inserted)
            self.persistent_gpio.payment_status.connect(self.payment_status_updated.emit)
            self._connected_gpio = self.persistent_gpio
            print("DEBUG: Signals connected successfully")

        # Setup coin timeout timer for persistent GPIO
        from PyQt5.QtCore import QTimer
        self.coin_timeout_timer = QTimer()
        self.coin_timeout_timer.timeout.connect(self.persistent_gpio.process_coin_timeout)
        self.coin_timeout_timer.start(100)  # Check every 100ms
        print("DEBUG: Coin timeout timer started")

    def enable_payment_mode(self):
        """Enables payment mode."""
        print(f"DEBUG: enable_payment_mode called, total_cost: {self.total_cost}")
        if self.total_cost <= 0:
            print("DEBUG: Total cost is 0 or negative, not enabling payment")
            return

        self.payment_ready = True
        print("DEBUG: payment_ready set to True")

        print(f"DEBUG: Checking if persistent_gpio exists: {hasattr(self, 'persistent_gpio')}")
        if hasattr(self, 'persistent_gpio'):
            print(f"DEBUG: persistent_gpio value: {self.persistent_gpio}")
            print("DEBUG: Calling persistent_gpio.enable_payment()")
            self.persistent_gpio.enable_payment()
            print("SUCCESS: Payment mode enabled via persistent GPIO")
        else:
            print("ERROR: No persistent GPIO available")

        status_text = "Payment mode enabled - Use simulation buttons" if not PAYMENT_GPIO_AVAILABLE else "Payment mode enabled - Insert coins or bills"
        self.payment_status_updated.emit(status_text)
        self.payment_mode_changed.emit(True)

    def disable_payment_mode(self):
        """Disables payment mode."""
        self.payment_ready = False
        if hasattr(self, 'persistent_gpio'):
            self.persistent_gpio.disable_payment()
            print("SUCCESS: Payment mode disabled via persistent GPIO")
        else:
            print("ERROR: No persistent GPIO available")

        status_text = "Payment mode disabled" + (" (Simulation)" if not PAYMENT_GPIO_AVAILABLE else "")
        self.payment_status_updated.emit(status_text)
        self.payment_mode_changed.emit(False)

    def on_coin_inserted(self, coin_value):
        """Handles coin insertion."""
        if not self.payment_ready:
            return

        self.amount_received += coin_value
        self.cash_received[coin_value] = self.cash_received.get(coin_value, 0) + 1
        self.amount_received_updated.emit(self.amount_received)
        self._update_payment_status()
        self.payment_status_updated.emit(f"P{coin_value} coin received")

    def on_bill_inserted(self, bill_value):
        """Handles bill insertion."""
        if not self.payment_ready:
            return

        self.amount_received += bill_value
        self.cash_received[bill_value] = self.cash_received.get(bill_value, 0) + 1
        self.amount_received_updated.emit(self.amount_received)
        self._update_payment_status()
        self.payment_status_updated.emit(f"P{bill_value} bill received")

    def simulate_coin(self, value):
        """Simulates coin insertion for testing."""
        if self.payment_ready:
            self.on_coin_inserted(value)

    def simulate_bill(self, value):
        """Simulates bill insertion for testing."""
        if self.payment_ready:
            self.on_bill_inserted(value)

    def _update_payment_status(self):
        """Updates payment status and calculates change."""
        try:
            # Prevent multiple automatic completions
            if hasattr(self, '_payment_completing') and self._payment_completing:
                print("WARNING: Payment already completing, ignoring duplicate trigger")
                return

            paid = self.amount_received + self.voucher_total
            if paid >= self.total_cost and self.total_cost > 0:
                change = paid - self.total_cost
                change_text = f"Payment Complete. Change: P{change:.2f}" if change > 0 else "Payment Complete"
                self.change_updated.emit(change, change_text)
                self.payment_button_enabled.emit(True)  # Enable payment button when sufficient payment

                if self.payment_ready and not (hasattr(self, '_payment_completing') and self._payment_completing):
                    self._payment_completing = True  # Prevent duplicate processing
                    self.payment_status_updated.emit("Payment sufficient - Processing automatically...")
                    self.disable_payment_mode()
                    # Automatically proceed to payment completion
                    self._auto_complete_payment()
            else:
                change_text = f"Remaining: P{self.amount_owed:.2f}"
                self.change_updated.emit(0, change_text)
                self.payment_button_enabled.emit(False)  # Disable payment button when insufficient payment

        except Exception as e:
            print(f"ERROR: Error in payment status update: {e}")
            self.payment_status_updated.emit(f"Payment error: {str(e)}")

        # Refresh inline suggestion each time status updates
        try:
            best = self.payment_algorithm.find_best_payment_amount(self.total_cost)
            self.best_payment_suggestion = best
            self.suggestion_updated.emit(self._format_best_payment_status())
        except Exception as e:
            print(f"Error refreshing best payment suggestion: {e}")

    def _format_best_payment_status(self) -> str:
        if not self.best_payment_suggestion:
            return ""
        amt = self.best_payment_suggestion.get('amount', self.total_cost)
        chg = self.best_payment_suggestion.get('change', 0)
        if chg == 0:
            per_job = f"Max payment we can receive: P{amt:.2f} (exact)"
        else:
            per_job = f"Max payment we can receive: P{amt:.2f} (available P{chg:.2f})"
        return f"{per_job}\n{MSG_UNGIVEN_CHANGE}"

    def _auto_complete_payment(self):
        """Automatically complete payment when sufficient amount is received."""
        print("Auto-completing payment...")

        # Show processing message
        self.payment_status_updated.emit("Dispensing change and preparing to print...")

        # Add a small delay to show the processing message
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1500, self._proceed_with_payment)

    def _proceed_with_payment(self):
        """Proceed with payment completion after delay."""
        print("Proceeding with payment completion...")

        # Check if we have main_app reference
        if hasattr(self, 'main_app') and self.main_app:
            # Call the existing complete_payment method
            success, message = self.complete_payment(self.main_app)
            if success:
                print("SUCCESS: Auto-payment completion successful")
            else:
                print(f"ERROR: Auto-payment completion failed: {message}")
                self.payment_status_updated.emit(f"Payment error: {message}")
        else:
            print("ERROR: No main_app reference available for auto-payment completion")
            self.payment_status_updated.emit("Payment completion failed - no app reference")

    def _check_payment_capabilities(self):
        """Check payment capabilities and emit suggestions to UI."""
        try:
            # Get payment suggestions
            suggestions = self.payment_algorithm.find_optimal_payment_amounts(self.total_cost)
            status_message = self.payment_algorithm.get_payment_status_message(self.total_cost)

            # Emit payment suggestions to UI
            self.payment_status_updated.emit(status_message)

            # Store suggestions for UI to display
            self.payment_suggestions = suggestions

            print(f"Payment capabilities checked. Status: {status_message}")
            print(f"Found {len(suggestions)} payment suggestions")

        except Exception as e:
            print(f"Error checking payment capabilities: {e}")
            self.payment_status_updated.emit("Error checking payment capabilities")

    def validate_payment_amount(self, payment_amount: float) -> Tuple[bool, str]:
        """Validate if a payment amount can be processed."""
        return self.payment_algorithm.validate_payment(self.total_cost, payment_amount)

    def get_payment_suggestions(self) -> List[Dict]:
        """Get payment suggestions for the current total cost."""
        return self.payment_algorithm.find_optimal_payment_amounts(self.total_cost)

    def settle_transaction(self):
        """Money is settled once change has been dispensed (cash taken, coins
        out, Shortfall Voucher saved, Applied Vouchers decremented), whatever
        the printer does next. Logs the transactions row as `paid` and applies
        the cash_inventory change, exactly once per payment_ref (#59). main_app
        later moves the row to `completed` or `print_failed`."""
        td = getattr(self, 'transaction_data', None)
        if not td:
            print("WARNING: No transaction data available to settle")
            return
        ref = td.get('payment_ref')
        if ref and ref == getattr(self, '_settled_ref', None):
            return
        td['status'] = 'paid'
        try:
            if not self.db_manager.log_transaction(td):
                print(f"ERROR: Transaction {ref} was not logged; skipping inventory update")
                return
            self._settled_ref = ref
            print(f"Transaction settled: {td['file_name']}")
        except Exception as e:
            print(f"ERROR: Error logging transaction: {e}")
            return
        try:
            for denom, count in (self.cash_received or {}).items():
                if count > 0:
                    self.db_manager.adjust_cash_inventory(denom, count, 'bill' if denom >= 20 else 'coin')
            for denom, count in (self.change_dispensed or {}).items():
                if count > 0:
                    self.db_manager.adjust_cash_inventory(denom, -count, 'bill' if denom >= 20 else 'coin')
        except Exception as e:
            print(f"ERROR: Error updating cash inventory: {e}")

    # Print job signals are now handled by the thank you screen
    # No need to connect them here since the thank you screen will manage the entire print lifecycle

    # calls voucher first

    def _navigate_to_thank_you(self):
        """Every post-dispense path ends here. If change went short, show the voucher
        (or the failure notice) first; the voucher screen calls continue_to_thank_you()
        when the customer is done."""
        if self._show_voucher_screen_if_needed():
            return
        self.continue_to_thank_you()

    def _show_voucher_screen_if_needed(self):
        outcome = self.outcome
        issued, failed, shortfall = outcome.voucher, outcome.voucher_failed, outcome.shortfall
        if not issued and not failed:
            return False
        try:
            screen = self.main_app.voucher_screen
            if issued:
                screen.show_issued(issued)
            else:
                screen.show_failure(shortfall)
            self.main_app.show_screen('voucher')
        except Exception as e:
            # Could not show it: carry on so the print still happens.
            print(f"CRITICAL: could not show the voucher screen: {e}")
            try:
                log_error("Voucher Not Shown",
                          f"A P{shortfall} voucher/notice could not be displayed: {e}", "payment_model")
            except Exception:
                pass
            return False
        # Handed off: the raw code now lives only on the voucher screen, and the
        # screen must not be shown twice. Only the cause is kept.
        self.outcome = ShortfallOutcome(cause=outcome.cause)
        return True

    # Print job success/failure handling is now done by the thank you screen
    # The thank you screen will monitor lpstat and handle print completion

    # Print timeout handling is now done by the thank you screen
    # The thank you screen will handle all print job monitoring and timeouts

    def continue_to_thank_you(self):
        """Navigate to thank you screen after all operations are complete."""
        print("DEBUG: _navigate_to_thank_you called")
        print("DEBUG: Current thread:", threading.current_thread().name)
        print("DEBUG: main_app available:", hasattr(self, 'main_app') and self.main_app is not None)

        if self.digital_refund is not None:
            self._show_digital_refund()
            return
        if self.digital_session is not None:
            session, self.digital_session = self.digital_session, None
            self.main_app.scan_result_screen.set_session(session, then_print=self.is_print_job())
            self.main_app.show_screen('scan_result')
            return
        if not self.is_print_job():
            self.main_app.show_screen('homepage')
            return

        try:
            # Emit payment completed signal now that everything is done
            if hasattr(self, 'payment_info') and self.payment_info:
                print("DEBUG: Emitting payment_completed signal with stored payment info")
                self.payment_completed.emit(self.payment_info)
            else:
                print("DEBUG: No payment info available to emit")

            if hasattr(self, 'main_app') and self.main_app:
                print("DEBUG: Navigating to thank you screen")
                self.main_app.show_screen('thank_you')
                print("DEBUG: Navigation to thank you screen completed")
            else:
                print("DEBUG: No main_app available for navigation")
        except Exception as e:
            print(f"ERROR: Exception in _navigate_to_thank_you: {e}")
            # Try to navigate anyway as a fallback
            try:
                if hasattr(self, 'main_app') and self.main_app:
                    self.main_app.show_screen('thank_you')
            except Exception as fallback_error:
                print(f"ERROR: Fallback navigation also failed: {fallback_error}")

    def on_enter(self):
        """Called when the payment screen is shown."""
        print("=== PAYMENT MODEL ON_ENTER START ===")
        print("Payment screen entered")
        print("DEBUG: About to call setup_gpio()")
        try:
            self.setup_gpio()
            print("DEBUG: setup_gpio() completed successfully")
        except Exception as e:
            print(f"DEBUG: setup_gpio() failed with error: {e}")

        # Reset payment state
        self.amount_received = 0
        self.cash_received = {}
        self.payment_processing = False
        # Only the change path cleared this, so an exact payment (no change,
        # e.g. Vouchers covering the cost) left the next customer unable to complete.
        self._payment_completing = False
        self.payment_ref = None
        self.outcome = ShortfallOutcome()
        self.change_owed = 0
        self.change_dispensed = {}
        self._cash_committed = False
        self._clear_vouchers()

        self.amount_received_updated.emit(0)
        self.change_updated.emit(0, "")

        # Automatically enable payment mode
        print("DEBUG: About to call enable_payment_mode()")
        self.enable_payment_mode()
        self._restore_carried_credit()
        print("=== PAYMENT MODEL ON_ENTER END ===")

    def _carry_unspent_cash(self):
        """Leaving with cash in and the payment not completed: hold the cash as
        Carried Credit rather than dropping it."""
        if self.amount_received <= 0 or self._cash_committed or not self.payment_data:
            return
        self.carried_credit = CarriedCredit(
            amount=int(self.amount_received), cash=dict(self.cash_received),
            payment_data=self.payment_data, total_cost=self.total_cost)
        print(f"Payment left unfinished: P{self.amount_received} kept as carried credit")
        self.amount_received = 0
        self.cash_received = {}

    def _restore_carried_credit(self):
        """Count the customer's Carried Credit toward this payment. Completes it
        straight away if it already covers the (possibly changed) price."""
        credit, self.carried_credit = self.carried_credit, None
        if not credit:
            return
        self.amount_received = credit.amount
        self.cash_received = dict(credit.cash)
        print(f"Carried credit restored: P{credit.amount}")
        self.amount_received_updated.emit(self.amount_received)
        self.payment_status_updated.emit(f"P{credit.amount} you already put in is counted")
        self._update_payment_status()

    def issue_voucher_for_carried_credit(self, continue_to):
        """The customer abandoned an unfinished payment with cash in: issue a Voucher
        for all of it, record the cancelled payment, and set up the voucher screen to
        continue to `continue_to`. Returns True if the voucher screen should be shown.
        With vouchers turned off, the cash is only recorded."""
        credit, self.carried_credit = self.carried_credit, None
        if not credit:
            return False
        payment_ref = uuid.uuid4().hex
        voucher, failed = None, False
        if self.db_manager.get_setting('vouchers_enabled', 1):
            try:
                voucher = VoucherManager(self.db_manager).issue(credit.amount, payment_ref=payment_ref)
            except Exception as e:
                failed = True
                print(f"CRITICAL: could not issue voucher for P{credit.amount} of unspent cash: {e}")
                try:
                    log_error("Voucher Issue Failed",
                              f"Could not issue a P{credit.amount} voucher for an abandoned payment "
                              f"(payment_ref={payment_ref}): {e}", "payment_model")
                except Exception:
                    pass
                try:
                    send_operator_alert(f"Kiosk could not save a P{credit.amount} voucher for an "
                                        f"unfinished payment. Customer was told to see the attendant. "
                                        f"Ref {payment_ref[:8]}")
                except Exception as e2:
                    print(f"WARNING: could not send operator alert: {e2}")
        self._log_partial_payment(credit, voucher.value if voucher else 0, payment_ref)
        if not voucher and not failed:
            return False  # vouchers are off

        def continue_on():
            self.main_app.show_screen(continue_to)
        screen = self.main_app.voucher_screen
        if voucher:
            screen.show_issued(voucher, reason='unspent', on_continue=continue_on)
        else:
            screen.show_failure(credit.amount, reason='unspent', on_continue=continue_on)
        return True

    def on_leave(self):
        """Called when leaving the payment screen."""
        print("=== PAYMENT MODEL ON_LEAVE START ===")
        print("Payment screen leaving")
        self._carry_unspent_cash()

        # Stop coin timeout timer
        if hasattr(self, 'coin_timeout_timer') and self.coin_timeout_timer is not None:
            self.coin_timeout_timer.stop()
            self.coin_timeout_timer = None
            print("DEBUG: Coin timeout timer stopped")

        # Disable payment but keep persistent GPIO running for other screens
        if hasattr(self, 'persistent_gpio'):
            print("DEBUG: About to call persistent_gpio.disable_payment()")
            self.persistent_gpio.disable_payment()
            print("DEBUG: persistent_gpio.disable_payment() completed")
            print("Persistent GPIO payment disabled (but GPIO kept alive for other screens)")
        else:
            print("ERROR: No persistent_gpio available to disable payment")

        # Payment is already disabled by persistent GPIO
        print("Payment screen cleanup completed")

        # Stop any running dispense thread
        if hasattr(self, 'dispense_thread') and self.dispense_thread:
            print("Stopping dispense thread...")
            try:
                if self.dispense_thread.isRunning():
                    self.dispense_thread.terminate()
                    self.dispense_thread.wait(1000)
            except Exception as e:
                print(f"Error stopping dispense thread: {e}")
            finally:
                # Clear the thread reference
                self.dispense_thread = None

        # Clean up change dispenser if it exists and is not being used
        if hasattr(self, 'change_dispenser') and self.change_dispenser:
            # Check if there's an active dispense thread
            if hasattr(self, 'dispense_thread') and self.dispense_thread and self.dispense_thread.isRunning():
                print("Payment screen: Skipping change dispenser cleanup - dispense thread still running")
            else:
                try:
                    print("Cleaning up change dispenser...")
                    self.change_dispenser.cleanup()
                except Exception as e:
                    print(f"Error cleaning up change dispenser: {e}")
                finally:
                    self.change_dispenser = None

    def _log_partial_payment(self, credit, voucher_value, payment_ref):
        """Record an abandoned payment's cash: a cancelled transaction (with the
        Voucher issued for it) and the cash added to inventory."""
        try:
            payment_data = credit.payment_data or {}

            # Defensive guards for keys
            pdf_data = payment_data.get('pdf_data') or {}
            selected_pages = payment_data.get('selected_pages') or []
            copies = int(payment_data.get('copies') or 1)
            color_mode = payment_data.get('color_mode') or 'Color'

            # Log cancelled transaction with partial payment
            transaction_data = {
                'file_name': _document_name(pdf_data) or "unknown.pdf",
                'pages': len(selected_pages),
                'copies': copies,
                'color_mode': color_mode,
                'total_cost': float(credit.total_cost or 0),
                'amount_paid': float(credit.amount),
                'change_given': 0,  # No change given since transaction cancelled
                'status': 'cancelled_partial_payment',
                'source': payment_data.get('source'),
                'change_dispensed': 0,
                'voucher_issued': voucher_value,
                'payment_ref': payment_ref,
            }
            try:
                self.db_manager.log_transaction(transaction_data)
            except Exception as log_err:
                print(f"WARNING: Failed to log cancelled transaction: {log_err}")

            # Safely increment cash inventory with received money (do not overwrite totals)
            try:
                current_inventory = {}
                for item in (self.db_manager.get_cash_inventory() or []):
                    if item.get('type') == 'coin' or item.get('type') == 'bill':
                        current_inventory[(item.get('type'), int(item.get('denomination')))] = int(item.get('count') or 0)

                for denomination, count in (credit.cash or {}).items():
                    if not count:
                        continue
                    is_bill = denomination >= 20
                    key = ('bill' if is_bill else 'coin', int(denomination))
                    new_count = current_inventory.get(key, 0) + int(count)
                    self.db_manager.update_cash_inventory(
                        denomination=int(denomination),
                        count=new_count,
                        type='bill' if is_bill else 'coin'
                    )
            except Exception as inv_err:
                print(f"WARNING: Failed to update cash inventory on cancel: {inv_err}")

            print(f"Logged cancelled transaction: {credit.amount} received, {credit.total_cost} required, "
                  f"voucher P{voucher_value}")
        except Exception as e:
            print(f"WARNING: _log_partial_payment encountered an error but will not block navigation: {e}")

    def complete_payment(self, main_app):
        """Complete the payment: record the transaction, dispense change,
        then hand off to printing. (Single definition; merged from the two
        former duplicates.)"""
        print("Starting payment completion process...")
        self.payment_ref = uuid.uuid4().hex

        # so a stale voucher can never reach the next user's screen
        self.outcome = ShortfallOutcome()

        try:
            # Validate payment data exists
            if not hasattr(self, 'payment_data') or self.payment_data is None:
                print("ERROR: No payment data available")
                return False, "No payment data available"

            # Validate main_app reference
            if not main_app:
                print("ERROR: No main app reference")
                return False, "No main app reference"

            if self.amount_received + self.voucher_total < self.total_cost:
                return False, "Payment is not sufficient."

            # Paper check (no decrement; main_app does that after a successful print).
            total_pages = len(self.payment_data['selected_pages']) * self.payment_data['copies']
            if self.is_print_job() and not main_app.admin_screen.check_paper_availability(total_pages):
                return False, (f"Not enough paper to complete print job.\n"
                               f"Required: {total_pages} sheets. Please contact administrator to refill paper.")

            # Take the Applied Vouchers' value now, all or nothing, before any
            # change comes out.
            voucher_applied = self._commit_vouchers()
            if voucher_applied is None:
                return False, "Could not apply your voucher. Please pay the rest in cash."
            self._cash_committed = True  # the cash now pays for this job, not Carried Credit

            # NOTE: payment_algorithm.validate_payment() is deliberately NOT
            # called here. With vouchers (ADR 0003) a sale must never be
            # blocked just because the hoppers can't make change.
            change_amount = self.amount_received + voucher_applied - self.total_cost
            self.change_owed = change_amount
            self.change_dispensed = {}
            print(f"Change to dispense: P{change_amount:.2f}")

            # Logged as 'paid' by settle_transaction() once change is out;
            # _issue_shortfall_voucher fills in change_dispensed / voucher_issued.
            self.transaction_data = {
                'file_name': _document_name(self.payment_data['pdf_data']),
                'pages': len(self.payment_data['selected_pages']),
                'copies': self.payment_data['copies'],
                'color_mode': self.payment_data['color_mode'],
                'total_cost': self.total_cost,
                'amount_paid': self.amount_received,
                'change_given': change_amount,
                'status': 'completed',
                'source': self.payment_data.get('source'),
                'change_dispensed': 0 if change_amount <= 0 else None,
                'voucher_issued': 0,
                'voucher_applied': voucher_applied,
                'payment_ref': self.payment_ref,
            }

            # Stop any existing dispense thread to prevent conflicts
            if self.dispense_thread and self.dispense_thread.isRunning():
                print("WARNING: Stopping existing dispense thread")
                self.dispense_thread.terminate()
                self.dispense_thread.wait(1000)
                self.dispense_thread = None

            if self.change_dispenser is None:
                self.change_dispenser = ChangeDispenser()
                print("SUCCESS: Change dispenser created")

            if change_amount > 0:
                print(f"Starting change dispensing for P{change_amount:.2f}")
                self.payment_status_updated.emit(f"Please wait... Dispensing change: P{change_amount:.2f}")
                # Only attempt the coins the hoppers hold; the rest is a predicted Shortfall.
                self.dispense_thread = DispenseThread(
                    dispenser=self.change_dispenser,
                    amount=change_amount,
                    admin_screen=main_app.admin_screen,
                    db_threader=main_app.db_threader,
                    coin_limits=self.payment_algorithm.get_coin_inventory()
                )
                self.dispense_thread.status_update.connect(self.payment_status_updated.emit)
                self.dispense_thread.dispensing_finished.connect(self._on_dispensing_finished)
                self.dispense_thread.start()
                print("SUCCESS: Dispense thread started")
            else:
                # No change to dispense, proceed directly to printing
                print("SUCCESS: No change to dispense, proceeding to printing")
                self._start_printing()

            return True, "Payment processing started"

        except Exception as e:
            print(f"ERROR: Error in payment completion: {e}")
            # Reset payment completing flag on error
            if hasattr(self, '_payment_completing'):
                self._payment_completing = False
            return False, f"Payment completion failed: {str(e)}"

    def _commit_vouchers(self):
        """Apply the Vouchers entered on this screen, linked to this payment.
        Returns the value Applied, or None if it failed: then nothing was taken
        off any Voucher, the Vouchers are dropped and the customer can pay the
        rest in cash (payment mode is re-enabled)."""
        if not self.applied_vouchers:
            return 0
        result = VoucherManager(self.db_manager).apply(
            [v.code for v in self.applied_vouchers], self.voucher_total, payment_ref=self.payment_ref)
        if result.success and result.total_applied == self.voucher_total:
            self.applied_vouchers = []  # the raw codes aren't needed any more
            return result.total_applied
        print(f"ERROR: could not apply vouchers at payment: {result.message}")
        try:
            log_error("Voucher Apply Failed",
                      f"Could not apply P{self.voucher_total} of vouchers "
                      f"(payment_ref={self.payment_ref}): {result.message}", "payment_model")
        except Exception:
            pass
        self._clear_vouchers()
        message = (result.message if result.status in (LookupStatus.USED, LookupStatus.EXPIRED)
                   else "Could not apply your voucher, please try again")
        self.voucher_message.emit(f"{message}. Please pay the rest in cash.", True)
        self._payment_completing = False
        self.enable_payment_mode()
        self._update_payment_status()
        return None

    def _on_dispensing_finished(self, result):
        """Change dispensing is done (fully, partly, or not at all): issue a
        Voucher for any shortfall, record what actually came out, then print.
        Coin inventory is updated by main_app after the print succeeds, using
        self.change_dispensed, so it is NOT updated here (that double-counted)."""
        print(f"Change dispensing finished: {result}")

        try:
            self._payment_completing = False

            if isinstance(result, dict):
                self.change_dispensed = {1: result.get('coins_1', 0), 5: result.get('coins_5', 0)}
            else:
                self.change_dispensed = {}

            self._issue_shortfall_voucher(result, self.change_owed)
            outcome = self.outcome
            if outcome.voucher_failed:
                self.payment_status_updated.emit(
                    f"Could not issue a voucher for P{outcome.shortfall}. Please contact the attendant.")
            elif outcome.shortfall and not outcome.voucher:
                print(f"WARNING: P{outcome.shortfall} change short and vouchers are disabled")

            # A hopper that stopped early but was made up with ₱1 coins left no Shortfall.
            if outcome.shortfall and not (isinstance(result, dict) and result.get('success', False)):
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else 'No result received'
                self.payment_status_updated.emit(f"Change dispensing failed: {error_msg}")

        except Exception as e:
            print(f"ERROR: Error handling dispensing completion: {e}")
            self.payment_status_updated.emit(f"Error processing change: {str(e)}")

        # Whatever happened with the change, the customer paid: print.
        self._start_printing()

    def _start_printing(self):
        """Start the printing process."""
        print("Starting printing process...")

        # The customer has paid and their change is out: settle now, before
        # anything about printing can go wrong.
        self.settle_transaction()

        try:
            # Validate payment data exists
            if not hasattr(self, 'payment_data') or not self.payment_data:
                print("ERROR: No payment data available for printing")
                self.payment_status_updated.emit("No payment data available for printing")
                return

            # Validate main app reference
            if not hasattr(self, 'main_app') or not self.main_app:
                print("ERROR: No main app reference for printing")
                self.payment_status_updated.emit("No main app reference for printing")
                return

            # Validate PDF data exists
            if 'pdf_data' not in self.payment_data or not self.payment_data['pdf_data']:
                print("ERROR: No PDF data available for printing")
                self.payment_status_updated.emit("No PDF data available for printing")
                return

            # The digital copy is created now that the sale is made, never before.
            self._prepare_digital_copy()

            if not self.is_print_job():
                # Digital-only: nothing to print. The sale was settled above, so
                # delivering the copy completes it (a failed copy stays `paid`).
                self.main_app.current_print_job = None
                if self.digital_refund is None:
                    record_print_success(self.db_manager, (getattr(self, 'transaction_data', None) or {}).get('payment_ref'))
                self._navigate_to_thank_you()
                return

            # Store print job details in main app for thank you screen
            print_job_details = {
                'file_path': self.payment_data['pdf_data']['path'],
                'selected_pages': self.payment_data.get('selected_pages', [1]),
                'copies': self.payment_data.get('copies', 1),
                'color_mode': self.payment_data.get('color_mode', 'Color'),
                # The print is async and the model resets, so the outcome is
                # recorded against this ref (#59).
                'payment_ref': (getattr(self, 'transaction_data', None) or {}).get('payment_ref'),
                # A failed digital copy's fee was already refunded (or flagged to the
                # attendant), so a failed print must not refund it again.
                'digital_fee_refunded': self.digital_fee() if self.digital_refund is not None else 0,
            }
            self.main_app.current_print_job = print_job_details
            print(f"SUCCESS: Print job details stored: {print_job_details}")

            # Navigate to thank you screen
            self._navigate_to_thank_you()

        except Exception as e:
            print(f"ERROR: Error starting printing: {e}")
            self.payment_status_updated.emit(f"Printing error: {str(e)}")
            # Try to navigate to thank you screen anyway
            try:
                self._navigate_to_thank_you()
            except Exception as nav_error:
                print(f"ERROR: Error navigating to thank you screen: {nav_error}")

    def _prepare_digital_copy(self):
        """Create the download/email session for a paid digital copy. If that
        fails, the fee is refunded as a Voucher (shown before moving on)."""
        self.digital_session = None
        self.digital_refund = None
        fee = self.digital_fee()
        if not fee:
            return
        failure = "unknown error"
        try:
            adapter = ScanAdapter(SessionManager(self.db_manager), get_config().scan_upload_dir)
            ok, message, session = adapter.handle_scan(self.payment_data['pdf_data']['path'])
            if ok:
                self.digital_session = session
                if not self.is_print_job():
                    # Copied for the session; a print job still needs the original.
                    shutil.rmtree(os.path.dirname(self.payment_data['pdf_data']['path']), ignore_errors=True)
                return
            failure = message
        except Exception as e:
            failure = str(e)
        print(f"ERROR: could not create the digital copy session: {failure}")
        try:
            log_error("Digital Copy Failed",
                      f"P{fee} was paid for a digital copy that couldn't be created "
                      f"(payment_ref={self.payment_ref}): {failure}", "payment_model")
        except Exception:
            pass
        try:
            voucher = VoucherManager(self.db_manager).issue(fee, payment_ref=self.payment_ref)
            self.digital_refund = ('issued', voucher)
            refunded = fee
        except Exception as e:
            print(f"CRITICAL: could not refund P{fee} as a voucher: {e}")
            self.digital_refund = ('failed', fee)
            refunded = 0
        # The row was settled before the copy was made, so record the refund on it.
        try:
            record_digital_refund(self.db_manager, (getattr(self, 'transaction_data', None) or {}).get('payment_ref'),
                                  refunded, digital_only=not self.is_print_job(), error_message=failure)
        except Exception as e:
            print(f"ERROR: could not record the digital refund on the transaction: {e}")

    def _show_digital_refund(self):
        kind, value = self.digital_refund
        self.digital_refund = None
        screen = self.main_app.voucher_screen
        if kind == 'issued':
            screen.show_issued(value, reason='digital_refund', on_continue=self.continue_to_thank_you)
        else:
            screen.show_failure(value, reason='digital_refund', on_continue=self.continue_to_thank_you)
        self.main_app.show_screen('voucher')

    def reset_payment_state(self):
        """Reset payment state for new transactions."""
        print("Resetting payment state...")

        try:
            # Reset payment completing flag
            if hasattr(self, '_payment_completing'):
                self._payment_completing = False

            # Reset payment amounts
            self.amount_received = 0
            self.total_cost = 0
            self.cash_received = {}
            self._clear_vouchers()

            # Reset payment data
            self.payment_data = None

            # Stop any running dispense thread
            if hasattr(self, 'dispense_thread') and self.dispense_thread and self.dispense_thread.isRunning():
                print("WARNING: Stopping dispense thread during reset")
                self.dispense_thread.terminate()
                self.dispense_thread.wait(1000)
                self.dispense_thread = None

            # Reset payment ready state
            self.payment_ready = False

            # Emit reset signals
            self.amount_received_updated.emit(0)
            self.change_updated.emit(0, "")
            self.payment_status_updated.emit("Payment screen ready")

            print("SUCCESS: Payment state reset complete")

        except Exception as e:
            print(f"ERROR: Error resetting payment state: {e}")

    @property
    def _payment_completing(self):
        return getattr(self, '_completing', False)

    @_payment_completing.setter
    def _payment_completing(self, value):
        # Also locks the screen (Back, Vouchers, timeout) while the payment completes.
        changed = value != self._payment_completing
        self._completing = value
        if changed:
            self.payment_locked.emit(value)

    def is_busy(self):
        """True while a paid payment is completing or change is coming out. Leaving
        then would stop the hoppers mid-payout and log a paid job as cancelled."""
        thread = getattr(self, 'dispense_thread', None)
        return self._payment_completing or bool(thread and thread.isRunning())

    def go_back(self):
        """Goes back to print options screen."""
        if self.is_busy():
            print("Payment screen: Back ignored, payment is completing / change is dispensing")
            return
        print("Payment screen: going back to print options")

        # on_leave() keeps any cash put in as Carried Credit for when payment reopens.
        self.on_leave()
        self.reset_payment_state()
        self.go_back_requested.emit()
