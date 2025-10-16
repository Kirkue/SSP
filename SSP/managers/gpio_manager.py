# managers/gpio_manager.py

import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QThread

try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("✅ pigpio library found. GPIO Manager is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("⚠️ pigpio library not found. GPIO Manager will be SIMULATED.")

class GPIOManager(QObject):
    """Centralized GPIO manager for the entire application."""
    
    # Global signals for all GPIO events
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.pi = None
        self.gpio_available = PIGPIO_AVAILABLE
        self.running = False
        self.payment_enabled = False
        
        # GPIO pins
        self.COIN_PIN = 17
        self.BILL_PIN = 18
        self.INHIBIT_PIN = 23
        
        # Timing constants
        self.DEBOUNCE_TIME = 0.05  # 50ms debounce
        self.COIN_TIMEOUT = 0.5    # 500ms timeout for coin counting
        self.BILL_TIMEOUT = 1.0    # 1s timeout for bill counting
        
        # State tracking
        self.coin_pulse_count = 0
        self.coin_last_pulse_time = 0
        self.bill_last_pulse_time = 0
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize GPIO if available
        if self.gpio_available:
            self._initialize_gpio()
    
    def _initialize_gpio(self):
        """Initialize GPIO connections."""
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise Exception("Could not connect to pigpio daemon")
            
            # Setup coin acceptor GPIO
            self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
            self.pi.callback(self.COIN_PIN, pigpio.FALLING_EDGE, self._coin_pulse_detected)
            
            # Setup bill acceptor GPIO
            self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
            self.pi.set_mode(self.INHIBIT_PIN, pigpio.OUTPUT)
            self.set_acceptor_state(False)  # Start disabled
            self.pi.callback(self.BILL_PIN, pigpio.FALLING_EDGE, self._bill_pulse_detected)
            
            self.running = True
            self.payment_status.emit("GPIO Manager initialized - Bill acceptor disabled")
            print("✅ GPIO Manager initialized successfully")
            
        except Exception as e:
            self.payment_status.emit(f"GPIO Error: {str(e)}")
            self.gpio_available = False
            print(f"❌ GPIO Manager initialization failed: {e}")
    
    def _coin_pulse_detected(self, gpio, level, tick):
        """Handle coin pulse detection."""
        with self._lock:
            current_time = time.time()
            if current_time - self.coin_last_pulse_time > self.DEBOUNCE_TIME:
                self.coin_pulse_count += 1
                self.coin_last_pulse_time = current_time
                print(f"🪙 Coin pulse detected: {self.coin_pulse_count}")
    
    def _bill_pulse_detected(self, gpio, level, tick):
        """Handle bill pulse detection."""
        with self._lock:
            current_time = time.time()
            if current_time - self.bill_last_pulse_time > self.DEBOUNCE_TIME:
                self.bill_last_pulse_time = current_time
                # Process bill detection
                self._process_bill_detection()
    
    def _process_bill_detection(self):
        """Process bill detection with timeout."""
        def process_bill():
            time.sleep(0.1)  # Wait for potential additional pulses
            with self._lock:
                if time.time() - self.bill_last_pulse_time >= 0.1:
                    # Bill detection complete
                    bill_value = self._get_bill_value()
                    if bill_value > 0:
                        self.bill_inserted.emit(bill_value)
                        print(f"💵 Bill detected: ₱{bill_value}")
        
        threading.Thread(target=process_bill, daemon=True).start()
    
    def _get_bill_value(self):
        """Get bill value based on pulse pattern (simplified)."""
        # This would need to be implemented based on your bill acceptor's pulse pattern
        # For now, return a default value
        return 20  # Default ₱20 bill
    
    def _get_coin_value(self, pulse_count):
        """Get coin value based on pulse count."""
        coin_values = {1: 1, 2: 5}  # 1 pulse = ₱1, 2 pulses = ₱5
        return coin_values.get(pulse_count, 0)
    
    def set_acceptor_state(self, enable):
        """Enable or disable the bill acceptor."""
        if self.gpio_available and self.pi:
            self.pi.write(self.INHIBIT_PIN, 0 if enable else 1)  # LOW = enabled, HIGH = disabled
            self.payment_enabled = enable
            print(f"Bill acceptor {'enabled' if enable else 'disabled'}")
        else:
            print(f"Bill acceptor {'enabled' if enable else 'disabled'} (simulation mode)")
    
    def enable_payment(self):
        """Enable payment processing."""
        self.payment_enabled = True
        self.set_acceptor_state(True)
        self.payment_status.emit("Payment enabled - Insert coins or bills")
    
    def disable_payment(self):
        """Disable payment processing."""
        self.payment_enabled = False
        self.set_acceptor_state(False)
        self.payment_status.emit("Payment disabled")
    
    def process_coin_timeout(self):
        """Process coin timeout and emit coin value if applicable."""
        if not self.payment_enabled:
            return
            
        with self._lock:
            if self.coin_pulse_count > 0 and (time.time() - self.coin_last_pulse_time > self.COIN_TIMEOUT):
                coin_value = self._get_coin_value(self.coin_pulse_count)
                if coin_value > 0:
                    self.coin_inserted.emit(coin_value)
                    print(f"🪙 Coin processed: ₱{coin_value}")
                self.coin_pulse_count = 0
    
    def cleanup(self):
        """Clean up GPIO resources."""
        print("🧹 Cleaning up GPIO Manager...")
        self.running = False
        
        if self.gpio_available and self.pi:
            try:
                self.set_acceptor_state(False)
                time.sleep(0.1)  # Small delay to ensure acceptor is disabled
                self.pi.stop()
                print("✅ GPIO Manager cleaned up successfully")
            except Exception as e:
                print(f"⚠️ Error during GPIO cleanup: {e}")
            finally:
                self.pi = None
    
    def is_available(self):
        """Check if GPIO is available."""
        return self.gpio_available and self.pi and self.pi.connected
    
    def get_status(self):
        """Get current GPIO status."""
        if self.is_available():
            return "GPIO Manager ready"
        elif self.gpio_available:
            return "GPIO Manager connected but not ready"
        else:
            return "GPIO Manager not available (simulation mode)"

# Global GPIO manager instance
_gpio_manager = None

def get_gpio_manager():
    """Get the global GPIO manager instance."""
    global _gpio_manager
    if _gpio_manager is None:
        _gpio_manager = GPIOManager()
    return _gpio_manager

def cleanup_gpio_manager():
    """Clean up the global GPIO manager."""
    global _gpio_manager
    if _gpio_manager:
        _gpio_manager.cleanup()
        _gpio_manager = None
