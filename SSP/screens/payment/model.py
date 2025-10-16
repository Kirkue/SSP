import os
import time
import threading
from typing import Tuple, List, Dict
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from managers.hopper_manager import ChangeDispenser, DispenseThread, PIGPIO_AVAILABLE as HOPPER_GPIO_AVAILABLE
from managers.payment_algorithm_manager import PaymentAlgorithmManager
from database.db_manager import DatabaseManager

try:
    import pigpio
    PAYMENT_GPIO_AVAILABLE = True
except ImportError:
    PAYMENT_GPIO_AVAILABLE = False
    print("Warning: pigpio module not available. GPIO payment acceptance will be disabled.")


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
        self.selected_pages = None
        self.copies = 1
        self.color_mode = "Color"

    def setup_gpio(self):
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise Exception("Could not connect to pigpio daemon")
            self.COIN_PIN, self.BILL_PIN, self.INHIBIT_PIN = 17, 18, 23
            
            # Setup coin acceptor GPIO (exactly like working code)
            self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
            self.pi.callback(self.COIN_PIN, pigpio.FALLING_EDGE, self.coin_pulse_detected)
            
            # Setup bill acceptor GPIO (exactly like working code)
            self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
            self.pi.set_mode(self.INHIBIT_PIN, pigpio.OUTPUT)
            self.set_acceptor_state(False)  # Start disabled
            self.pi.callback(self.BILL_PIN, pigpio.FALLING_EDGE, self.bill_pulse_detected)
            
            self.payment_status.emit("Payment system ready - Bill acceptor disabled")
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
        
    def set_payment_data(self, payment_data):
        """Sets the payment data and initializes payment state."""
        self.payment_data = payment_data
        self.total_cost = payment_data['total_cost']
        self.amount_received = 0
        self.cash_received = {}
        self.payment_ready = False
        
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
        doc_name = os.path.basename(payment_data['pdf_data']['path'])
        
        summary_data = {
            'total_cost': self.total_cost,
            'document_name': doc_name,
            'copies': payment_data['copies'],
            'color_mode': payment_data['color_mode'],
            'black_pages': b_count,
            'color_pages': c_count
        }
        
        self.payment_data_updated.emit(summary_data)
        self.payment_status_updated.emit("Click 'Enable Payment' to begin")
    
    def setup_gpio(self):
        """Sets up the GPIO payment thread."""
        self.gpio_thread = GPIOPaymentThread()
        self.gpio_thread.coin_inserted.connect(self.on_coin_inserted)
        self.gpio_thread.bill_inserted.connect(self.on_bill_inserted)
        self.gpio_thread.payment_status.connect(self.payment_status_updated.emit)
        self.gpio_thread.enable_acceptor.connect(self.gpio_thread.set_acceptor_state)
        self.gpio_thread.start()
    
    def enable_payment_mode(self):
        """Enables payment mode."""
        if self.total_cost <= 0:
            return
        
        self.payment_ready = True
        if self.gpio_thread:
            self.gpio_thread.enable_acceptor.emit(True)
        
        status_text = "Payment mode enabled - Use simulation buttons" if not PAYMENT_GPIO_AVAILABLE else "Payment mode enabled - Insert coins or bills"
        self.payment_status_updated.emit(status_text)
        self.payment_mode_changed.emit(True)
    
    def disable_payment_mode(self):
        """Disables payment mode."""
        self.payment_ready = False
        if self.gpio_thread:
            self.gpio_thread.enable_acceptor.emit(False)
        
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
        self.payment_status_updated.emit(f"₱{coin_value} coin received")
    
    def on_bill_inserted(self, bill_value):
        """Handles bill insertion."""
        if not self.payment_ready:
            return
        
        self.amount_received += bill_value
        self.cash_received[bill_value] = self.cash_received.get(bill_value, 0) + 1
        self.amount_received_updated.emit(self.amount_received)
        self._update_payment_status()
        self.payment_status_updated.emit(f"₱{bill_value} bill received")
    
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
        if self.amount_received >= self.total_cost and self.total_cost > 0:
            change = self.amount_received - self.total_cost
            change_text = f"Payment Complete. Change: ₱{change:.2f}" if change > 0 else "Payment Complete"
            self.change_updated.emit(change, change_text)
            self.payment_button_enabled.emit(True)  # Enable payment button when sufficient payment
            
            if self.payment_ready:
                self.payment_status_updated.emit("Payment sufficient - Ready to print")
                self.disable_payment_mode()
        else:
            remaining = self.total_cost - self.amount_received
            change_text = f"Remaining: ₱{remaining:.2f}"
            self.change_updated.emit(0, change_text)
            self.payment_button_enabled.emit(False)  # Disable payment button when insufficient payment

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
            return f"Max payment we can receive: ₱{amt:.2f} (exact)"
        return f"Max payment we can receive: ₱{amt:.2f} (available ₱{chg:.2f})"
    
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
    
    def complete_payment(self, main_app):
        """Completes the payment process."""
        if self.amount_received < self.total_cost:
            return False, "Payment is not sufficient."
        
        # Validate payment with algorithm
        is_valid, message, payment_info = self.payment_algorithm.validate_payment(
            self.total_cost, self.amount_received
        )
        
        if not is_valid:
            return False, f"Payment cannot be processed: {message}"
        
        # Check paper availability
        total_pages = len(self.payment_data['selected_pages']) * self.payment_data['copies']
        admin_screen = main_app.admin_screen
        if not admin_screen.update_paper_count(total_pages):
            return False, f"Not enough paper to complete print job.\nRequired: {total_pages} sheets. Please contact administrator to refill paper."
        
        # Process transaction
        change_amount = self.amount_received - self.total_cost
        transaction_data = {
            'file_name': os.path.basename(self.payment_data['pdf_data']['path']),
            'pages': len(self.payment_data['selected_pages']),
            'copies': self.payment_data['copies'],
            'color_mode': self.payment_data['color_mode'],
            'total_cost': self.total_cost,
            'amount_paid': self.amount_received,
            'change_given': change_amount,
            'status': 'completed'
        }
        self.db_manager.log_transaction(transaction_data)
        
        # Update cash inventory
        for denomination, count in self.cash_received.items():
            self.db_manager.update_cash_inventory(
                denomination=denomination, 
                count=count, 
                type='bill' if denomination >= 20 else 'coin'
            )
        
        # Store payment info for later emission (after hopper dispensing and printing)
        self.payment_info = {
            'pdf_data': self.payment_data['pdf_data'],
            'selected_pages': self.payment_data['selected_pages'],
            'color_mode': self.payment_data['color_mode'],
            'copies': self.payment_data['copies'],
            'total_cost': self.total_cost,
            'amount_received': self.amount_received,
            'change': change_amount,
            'payment_method': 'Cash' if PAYMENT_GPIO_AVAILABLE else 'Simulation'
        }
        
        print("DEBUG: Payment info stored, will emit after hopper dispensing and printing complete")
        
        # NEW FLOW: Handle change dispensing FIRST, then print
        if change_amount > 0:
            print(f"DEBUG: Starting change dispensing for ₱{change_amount:.2f}")
            self.payment_status_updated.emit(f"Please wait... Dispensing change: ₱{change_amount:.2f}")
            print("DEBUG: Payment screen will stay active during hopper dispensing")
            
            # Ensure change dispenser is available
            if not hasattr(self, 'change_dispenser') or self.change_dispenser is None:
                print("DEBUG: Change dispenser not available, creating new one")
                self.change_dispenser = ChangeDispenser()
            
            # Get admin screen from main_app to pass to dispense thread
            admin_screen = None
            if hasattr(self, 'main_app') and hasattr(self.main_app, 'admin_screen'):
                admin_screen = self.main_app.admin_screen
                print(f"DEBUG: Admin screen found: {admin_screen}")
            else:
                print("DEBUG: No admin screen found")
            
            # Get database thread manager from main_app
            db_threader = None
            if hasattr(self, 'main_app') and hasattr(self.main_app, 'db_threader'):
                db_threader = self.main_app.db_threader
                print(f"DEBUG: Database threader found: {db_threader}")
            else:
                print("DEBUG: No database threader found")
            
            self.dispense_thread = DispenseThread(
                self.change_dispenser, 
                change_amount, 
                admin_screen, 
                db_threader
            )
            self.dispense_thread.status_update.connect(self.payment_status_updated.emit)
            self.dispense_thread.dispensing_finished.connect(self._on_dispensing_finished)
            self.dispense_thread.start()
            print("DEBUG: Dispense thread started")
        else:
            print("DEBUG: No change to dispense, starting printing directly")
            self._start_printing()
        
        return True, "Payment completed successfully"
    
    # Print job signals are now handled by the thank you screen
    # No need to connect them here since the thank you screen will manage the entire print lifecycle
    
    def _on_dispensing_finished(self, result):
        """Handles the completion of change dispensing."""
        print(f"DEBUG: _on_dispensing_finished called with result={result}")
        
        try:
            if isinstance(result, dict) and result.get('success', False):
                # New flow: Update database with actual coins dispensed, then print
                coins_1 = result.get('coins_1', 0)
                coins_5 = result.get('coins_5', 0)
                actual_change = result.get('actual_change', 0)
                expected_change = result.get('expected_change', 0)
                
                print(f"DEBUG: Change dispensing completed - ₱1={coins_1}, ₱5={coins_5}, actual={actual_change}, expected={expected_change}")
                self.payment_status_updated.emit(f"Change dispensed! Updating inventory...")
                
                # Update database with actual coins dispensed
                if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'db_threader') and self.main_app.db_threader:
                    print("DEBUG: Updating coin inventory in database...")
                    self.main_app.db_threader.update_coin_inventory(
                        coins_1, coins_5, 
                        callback=self._on_coin_inventory_updated
                    )
                else:
                    print("DEBUG: No database thread manager available, proceeding to print")
                    self._start_printing()
            else:
                # Fallback for old boolean format
                print(f"DEBUG: Old format result: {result}")
                if result:
                    print("Dispensing complete.")
                    self._start_printing()
                else:
                    print("CRITICAL: Error dispensing change.")
                    self._navigate_to_thank_you()
        except Exception as e:
            print(f"ERROR: Exception in _on_dispensing_finished: {e}")
            # Fallback to navigation even if there's an error
            self._navigate_to_thank_you()
        
        # Clean up change dispenser after dispensing is complete
        try:
            if hasattr(self, 'change_dispenser') and self.change_dispenser:
                print("DEBUG: Cleaning up change dispenser after dispensing complete")
                self.change_dispenser.cleanup()
                # Don't set to None here as it might be needed for future transactions
        except Exception as e:
            print(f"DEBUG: Error cleaning up change dispenser: {e}")
        
        # Clean up the dispense thread
        try:
            if hasattr(self, 'dispense_thread') and self.dispense_thread:
                print("DEBUG: Cleaning up dispense thread after completion")
                if self.dispense_thread.isRunning():
                    self.dispense_thread.terminate()
                    self.dispense_thread.wait(1000)
                self.dispense_thread = None
        except Exception as e:
            print(f"DEBUG: Error cleaning up dispense thread: {e}")
    
    def _on_coin_inventory_updated(self, operation):
        """Handles the completion of coin inventory update."""
        print(f"DEBUG: Coin inventory updated: {operation.result}")
        if operation.error:
            print(f"ERROR: Failed to update coin inventory: {operation.error}")
            self.payment_status_updated.emit("Inventory update failed, but continuing...")
        else:
            print("DEBUG: Coin inventory successfully updated")
            self.payment_status_updated.emit("Inventory updated successfully!")
        
        # Store print job details in main app for thank you screen to access
        if hasattr(self, 'main_app') and hasattr(self, 'print_file_path'):
            print("DEBUG: Storing print job details in main app...")
            self.main_app.current_print_job = {
                'file_path': self.print_file_path,
                'selected_pages': self.selected_pages,
                'copies': self.copies,
                'color_mode': self.color_mode
            }
            print(f"DEBUG: Print job details stored: {self.main_app.current_print_job}")
        
        # Navigate directly to thank you screen after change dispensing
        print("DEBUG: Change dispensing complete, navigating to thank you screen...")
        self._navigate_to_thank_you()
    
    def _start_printing(self):
        """Start the printing process after change has been dispensed."""
        print("DEBUG: Starting printing process...")
        self.payment_status_updated.emit("Change dispensed. Starting to print...")
        
        # Ensure print attributes exist (defensive programming)
        if not hasattr(self, 'print_file_path'):
            print("ERROR: print_file_path attribute not found, initializing...")
            self.print_file_path = None
        if not hasattr(self, 'selected_pages'):
            print("ERROR: selected_pages attribute not found, initializing...")
            self.selected_pages = None
        if not hasattr(self, 'copies'):
            print("ERROR: copies attribute not found, initializing...")
            self.copies = 1
        if not hasattr(self, 'color_mode'):
            print("ERROR: color_mode attribute not found, initializing...")
            self.color_mode = "Color"
        
        # Try to get print attributes from payment_data if they're not set
        if not self.print_file_path and hasattr(self, 'payment_data') and self.payment_data:
            print("DEBUG: Attempting to extract print attributes from payment_data...")
            if 'pdf_data' in self.payment_data and 'path' in self.payment_data['pdf_data']:
                self.print_file_path = self.payment_data['pdf_data']['path']
            if 'selected_pages' in self.payment_data:
                self.selected_pages = self.payment_data['selected_pages']
            if 'copies' in self.payment_data:
                self.copies = self.payment_data['copies']
            if 'color_mode' in self.payment_data:
                self.color_mode = self.payment_data['color_mode']
            print(f"DEBUG: Extracted from payment_data - file: {self.print_file_path}, pages: {self.selected_pages}, copies: {self.copies}, mode: {self.color_mode}")
        
        # Check if all required print attributes are available
        if not self.print_file_path:
            print("ERROR: No print file path available")
            self.payment_status_updated.emit("Error: No print file path available")
            self._navigate_to_thank_you()
            return
            
        if not self.selected_pages:
            print("ERROR: No selected pages available")
            self.payment_status_updated.emit("Error: No selected pages available")
            self._navigate_to_thank_you()
            return
        
        print(f"DEBUG: Print job details - file: {self.print_file_path}, pages: {self.selected_pages}, copies: {self.copies}, mode: {self.color_mode}")
        
        # Store print job details in main app for thank you screen to access
        if hasattr(self, 'main_app'):
            print("DEBUG: Storing print job details in main app...")
            self.main_app.current_print_job = {
                'file_path': self.print_file_path,
                'selected_pages': self.selected_pages,
                'copies': self.copies,
                'color_mode': self.color_mode
            }
            print(f"DEBUG: Print job details stored: {self.main_app.current_print_job}")
        
        # Don't start the print job here - let the thank you screen handle it
        # The thank you screen will start the print job and monitor it properly
        print("DEBUG: Print job details prepared, navigating to thank you screen...")
        print("DEBUG: Thank you screen will start the print job and monitor completion")
        self._navigate_to_thank_you()
    
    # Print job success/failure handling is now done by the thank you screen
    # The thank you screen will monitor lpstat and handle print completion
    
    # Print timeout handling is now done by the thank you screen
    # The thank you screen will handle all print job monitoring and timeouts
    
    def _navigate_to_thank_you(self):
        """Navigate to thank you screen after all operations are complete."""
        print("DEBUG: _navigate_to_thank_you called")
        print("DEBUG: Current thread:", threading.current_thread().name)
        print("DEBUG: main_app available:", hasattr(self, 'main_app') and self.main_app is not None)
        
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
        print("Payment screen entered")
        self.setup_gpio()
        
        # Reset payment state
        self.payment_ready = False
        self.amount_received = 0
        self.cash_received = {}
        self.payment_processing = False
        
        self.amount_received_updated.emit(0)
        self.change_updated.emit(0, "")
        self.payment_status_updated.emit("Click 'Enable Payment' to begin")
    
    def on_leave(self):
        """Called when leaving the payment screen."""
        print("Payment screen leaving")
        
        # Stop GPIO thread safely
        if hasattr(self, 'gpio_thread') and self.gpio_thread:
            print("Stopping GPIO thread...")
            try:
                self.gpio_thread.stop()
                if not self.gpio_thread.wait(2000):
                    print("Warning: GPIO thread did not stop gracefully")
                    self.gpio_thread.terminate()
                    self.gpio_thread.wait(1000)
            except Exception as e:
                print(f"Error stopping GPIO thread: {e}")
            finally:
                # Clear the thread reference
                self.gpio_thread = None
        
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
    
    def _log_partial_payment(self):
        """Log partial payment when user cancels transaction."""
        if self.amount_received > 0 and self.payment_data:
            # Log cancelled transaction with partial payment
            transaction_data = {
                'file_name': os.path.basename(self.payment_data['pdf_data']['path']),
                'pages': len(self.payment_data['selected_pages']),
                'copies': self.payment_data['copies'],
                'color_mode': self.payment_data['color_mode'],
                'total_cost': self.total_cost,
                'amount_paid': self.amount_received,
                'change_given': 0,  # No change given since transaction cancelled
                'status': 'cancelled_partial_payment'
            }
            self.db_manager.log_transaction(transaction_data)
            
            # Update cash inventory with received money (even though transaction cancelled)
            for denomination, count in self.cash_received.items():
                self.db_manager.update_cash_inventory(
                    denomination=denomination, 
                    count=count, 
                    type='bill' if denomination >= 20 else 'coin'
                )
            
            print(f"Logged cancelled transaction: {self.amount_received} received, {self.total_cost} required")

    def go_back(self):
        """Goes back to print options screen."""
        print("Payment screen: going back to print options")
        
        # Log partial payment if user received cash but cancelled
        self._log_partial_payment()
        
        self.on_leave()
        self.payment_data = None
        self.go_back_requested.emit()
