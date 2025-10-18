# managers/persistent_gpio.py

import time
import threading
from PyQt5.QtCore import QObject, pyqtSignal

try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("SUCCESS: pigpio library found. Persistent GPIO is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("WARNING: pigpio library not found. Persistent GPIO will be SIMULATED.")

class PersistentGPIO(QObject):
    """Singleton GPIO service that maintains a persistent pigpio connection."""
    
    # Global signals
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Always call parent __init__ first
        super().__init__()
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.pi = None
        self.gpio_available = PIGPIO_AVAILABLE
        self.enabled = False
        self.running = False
        
        # GPIO pins
        self.COIN_PIN = 17
        self.BILL_PIN = 18
        self.INHIBIT_PIN = 23
        self.COIN_INHIBIT_PIN = 22
        
        # Timing constants (matching original GPIOPaymentThread)
        self.DEBOUNCE_TIME = 0.1   # Minimum time between pulses
        self.COIN_TIMEOUT = 0.5    # seconds without pulses = end of coin
        self.BILL_TIMEOUT = 0.5    # Time to wait for additional bill pulses (PULSE_TIMEOUT)
        
        # State tracking
        self.coin_pulse_count = 0
        self.coin_last_pulse_time = 0
        self.bill_pulse_count = 0
        self.bill_last_pulse_time = 0
        
        # Callbacks
        self.coin_callback = None
        self.bill_callback = None
        
        # Thread safety
        self._state_lock = threading.Lock()
        
        # Initialize GPIO if available
        if self.gpio_available:
            self._initialize_gpio()
    
    def _initialize_gpio(self):
        """Initialize persistent GPIO connection."""
        try:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                raise Exception("Could not connect to pigpio daemon")
            
            # Setup coin acceptor GPIO
            self.pi.set_mode(self.COIN_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.COIN_PIN, pigpio.PUD_UP)
            self.coin_callback = self.pi.callback(self.COIN_PIN, pigpio.FALLING_EDGE, self._coin_pulse_detected)
            
            # Setup coin acceptor inhibit pin (pin 22)
            self.pi.set_mode(self.COIN_INHIBIT_PIN, pigpio.OUTPUT)
            self._set_coin_acceptor_state(False)  # Start disabled
            
            # Setup bill acceptor GPIO
            self.pi.set_mode(self.BILL_PIN, pigpio.INPUT)
            self.pi.set_pull_up_down(self.BILL_PIN, pigpio.PUD_UP)
            self.pi.set_mode(self.INHIBIT_PIN, pigpio.OUTPUT)
            self._set_acceptor_state(False)  # Start disabled
            self.bill_callback = self.pi.callback(self.BILL_PIN, pigpio.FALLING_EDGE, self._bill_pulse_detected)
            
            self.running = True
            self.payment_status.emit("Persistent GPIO ready - Coin and bill acceptors disabled")
            print("SUCCESS: Persistent GPIO initialized successfully")
            
        except Exception as e:
            self.payment_status.emit(f"GPIO Error: {str(e)}")
            self.gpio_available = False
            print(f"ERROR: Persistent GPIO initialization failed: {e}")
    
    def _coin_pulse_detected(self, gpio, level, tick):
        """Handle coin pulse detection."""
        if not self.enabled:
            return
            
        current_time = time.time()
        with self._state_lock:
            if current_time - self.coin_last_pulse_time > self.DEBOUNCE_TIME:
                self.coin_pulse_count += 1
                self.coin_last_pulse_time = current_time
                print(f"Coin pulse detected: {self.coin_pulse_count}")
    
    def _bill_pulse_detected(self, gpio, level, tick):
        """Handle bill pulse detection."""
        if not self.enabled:
            return
            
        current_time = time.time()
        with self._state_lock:
            if current_time - self.bill_last_pulse_time > self.DEBOUNCE_TIME:
                self.bill_pulse_count += 1
                self.bill_last_pulse_time = current_time
                print(f"Bill pulse detected: {self.bill_pulse_count}")
    
    def _set_acceptor_state(self, enable):
        """Enable or disable the bill acceptor."""
        print(f"DEBUG: _set_acceptor_state called with enable={enable}")
        if self.gpio_available and self.pi and self.pi.connected:
            pin_value = 0 if enable else 1
            print(f"DEBUG: Writing to INHIBIT_PIN {self.INHIBIT_PIN} with value {pin_value}")
            self.pi.write(self.INHIBIT_PIN, pin_value)  # LOW = enabled, HIGH = disabled
            print(f"Bill acceptor {'enabled' if enable else 'disabled'}")
        else:
            print(f"Bill acceptor {'enabled' if enable else 'disabled'} (simulation mode)")
    
    def _set_coin_acceptor_state(self, enable):
        """Enable or disable the coin acceptor."""
        print(f"DEBUG: _set_coin_acceptor_state called with enable={enable}")
        if self.gpio_available and self.pi and self.pi.connected:
            pin_value = 1 if enable else 0
            print(f"DEBUG: Writing to COIN_INHIBIT_PIN {self.COIN_INHIBIT_PIN} with value {pin_value}")
            self.pi.write(self.COIN_INHIBIT_PIN, pin_value)  # HIGH = enabled, LOW = disabled
            print(f"Coin acceptor {'enabled' if enable else 'disabled'}")
        else:
            print(f"Coin acceptor {'enabled' if enable else 'disabled'} (simulation mode)")
    
    def enable_payment(self):
        """Enable payment processing."""
        self.enabled = True
        self._set_acceptor_state(True)  # Enable bill acceptor
        self._set_coin_acceptor_state(True)  # Enable coin acceptor
        self.payment_status.emit("Payment enabled - Insert coins or bills")
        print("SUCCESS: Persistent GPIO payment enabled")
    
    def disable_payment(self):
        """Disable payment processing."""
        print("DEBUG: disable_payment() called")
        self.enabled = False
        print("DEBUG: About to disable bill acceptor")
        self._set_acceptor_state(False)  # Disable bill acceptor
        print("DEBUG: About to disable coin acceptor")
        self._set_coin_acceptor_state(False)  # Disable coin acceptor
        self.payment_status.emit("Payment disabled")
        print("SUCCESS: Persistent GPIO payment disabled")
    
    def process_coin_timeout(self):
        """Process coin timeout and emit coin value if applicable."""
        if not self.enabled:
            return
            
        with self._state_lock:
            current_time = time.time()
            
            # Process coin timeout
            if self.coin_pulse_count > 0 and (current_time - self.coin_last_pulse_time > self.COIN_TIMEOUT):
                coin_value = self._get_coin_value(self.coin_pulse_count)
                if coin_value > 0:
                    self.coin_inserted.emit(coin_value)
                    print(f"Coin processed: ₱{coin_value}")
                self.coin_pulse_count = 0
            
            # Process bill timeout
            if self.bill_pulse_count > 0 and (current_time - self.bill_last_pulse_time > self.BILL_TIMEOUT):
                bill_value = self._get_bill_value(self.bill_pulse_count)
                if bill_value > 0:
                    self.bill_inserted.emit(bill_value)
                    print(f"Bill processed: ₱{bill_value}")
                self.bill_pulse_count = 0
    
    def _get_coin_value(self, pulse_count):
        """Get coin value based on pulse count (matching original GPIOPaymentThread)."""
        if pulse_count == 1:
            return 1
        elif 5 <= pulse_count <= 7:
            return 5
        elif 10 <= pulse_count <= 12:
            return 10
        elif 18 <= pulse_count <= 21:
            return 20
        return 0
    
    def _get_bill_value(self, pulse_count):
        """Get bill value based on pulse count (matching original GPIOPaymentThread)."""
        if pulse_count == 2:
            return 20
        elif pulse_count == 5:
            return 50
        elif pulse_count == 10:
            return 100
        elif pulse_count == 50:
            return 500
        return 0
    
    def is_connected(self):
        """Check if GPIO is connected and running."""
        return self.gpio_available and self.pi and self.pi.connected and self.running
    
    def get_status(self):
        """Get current GPIO status."""
        if self.is_connected():
            return "Persistent GPIO ready"
        elif self.gpio_available:
            return "Persistent GPIO connected but not ready"
        else:
            return "Persistent GPIO not available (simulation mode)"
    
    def cleanup(self):
        """Clean up GPIO resources (only called on app shutdown)."""
        print("Cleaning up Persistent GPIO...")
        self.running = False
        self.enabled = False
        
        if self.gpio_available and self.pi:
            try:
                # Cancel callbacks
                if self.coin_callback:
                    self.coin_callback.cancel()
                    self.coin_callback = None
                if self.bill_callback:
                    self.bill_callback.cancel()
                    self.bill_callback = None
                
                # Disable acceptor
                self._set_acceptor_state(False)
                time.sleep(0.1)  # Small delay for state change
                
                # Stop pigpio
                self.pi.stop()
                print("SUCCESS: Persistent GPIO cleaned up successfully")
            except Exception as e:
                print(f"WARNING: Error during Persistent GPIO cleanup: {e}")
            finally:
                self.pi = None

# Global instance
_persistent_gpio = None

def get_persistent_gpio():
    """Get the global persistent GPIO instance."""
    global _persistent_gpio
    if _persistent_gpio is None:
        _persistent_gpio = PersistentGPIO()
    return _persistent_gpio

def cleanup_persistent_gpio():
    """Clean up the global persistent GPIO instance."""
    global _persistent_gpio
    if _persistent_gpio:
        _persistent_gpio.cleanup()
        _persistent_gpio = None
