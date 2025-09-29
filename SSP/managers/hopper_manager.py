# screens/hopper_manager.py

import time
from PyQt5.QtCore import QThread, pyqtSignal

# --- Check for pigpio and set a flag ---
try:
    import pigpio
    PIGPIO_AVAILABLE = True
    print("OK - pigpio library found. Hopper control is ENABLED.")
except ImportError:
    PIGPIO_AVAILABLE = False
    print("WARNING: pigpio library not found. Hopper control will be SIMULATED.")


# --- General Configuration ---
COIN_DELAY = 1.0         # Delay after a successful dispense before next one
DISPENSING_TIMEOUT = 10  # Maximum time to wait for a single coin
MAX_RETRY_ATTEMPTS = 5   # Maximum attempts per coin before giving up (increased from 3)
RETRY_DELAY = 0.5        # Delay between retry attempts

# --- Centralized configuration for the two hoppers ---
# Hopper A dispenses 1-peso coins
# Hopper B dispenses 5-peso coins
HOPPER_CONFIGS = {
    'A': {
        'signal_pin': 21,  # Coin pulse input for Hopper A  1 Peso
        'enable_pin': 16   # Hopper enable control for Hopper A
    },
    'B': {
        'signal_pin': 6,   # Coin pulse input for Hopper B
        'enable_pin': 26   # Hopper enable control for Hopper B
    }
}


class HopperController:
    """
    Controls a single coin hopper motor and sensor.
    This class is adapted from the user-provided script.
    """
    def __init__(self, pi_instance, name, signal_pin, enable_pin):
        self.pi = pi_instance
        self.name = name
        self.signal_pin = signal_pin
        self.enable_pin = enable_pin
        self.enabled = False
        self.dispensing = False
        self.coin_passage_count = 0
        self.sensor_active = False
        self.last_sensor_change = 0

        if PIGPIO_AVAILABLE and self.pi.connected:
            # Setup GPIO exactly like working code
            self.pi.set_mode(self.signal_pin, pigpio.INPUT)
            self.pi.set_pull_up_down(self.signal_pin, pigpio.PUD_UP)
            self.pi.set_mode(self.enable_pin, pigpio.OUTPUT)
            
            # Monitor both rising and falling edges to track coin passage
            self.callback = self.pi.callback(self.signal_pin, pigpio.EITHER_EDGE, self._sensor_callback)
            
            # Start with hopper disabled
            self._disable_hopper()
        else:
            self.callback = None

    def _enable_hopper(self):
        self.pi.write(self.enable_pin, 0) # Active low
        self.enabled = True
        print(f"[{self.name}] Hopper motor ENABLED")

    def _disable_hopper(self):
        self.pi.write(self.enable_pin, 1) # Inactive high
        self.enabled = False

    def _sensor_callback(self, gpio, level, tick):
        current_time = self.pi.get_current_tick()

        if level == 0:  # Falling edge - coin detected
            if not self.sensor_active:
                self.sensor_active = True
                self.last_sensor_change = current_time
                print(f"[{self.name}] SENSOR: Coin entering sensor")
        else:  # Rising edge - coin cleared
            if self.sensor_active:
                self.sensor_active = False
                # pigpio tick is a 32-bit unsigned int, handle wraparound
                elapsed = pigpio.tickDiff(self.last_sensor_change, current_time) / 1000000.0
                if elapsed > 0.01:  # Debounce: Minimum time for valid coin passage (10ms)
                    self.coin_passage_count += 1
                    print(f"[{self.name}] SENSOR: Coin passage complete (took {elapsed:.3f}s). Total passages in this cycle: {self.coin_passage_count}")
                else:
                    print(f"[{self.name}] SENSOR: False trigger (pulse too short: {elapsed:.3f}s)")

    def _wait_for_coin_passage(self):
        """Wait for exactly one coin passage through the sensor."""
        print(f"[{self.name}] Waiting for exactly one coin passage...")

        # Reset detection counters for this attempt
        self.coin_passage_count = 0
        self.sensor_active = False

        timeout_start = time.time()
        while (time.time() - timeout_start) < DISPENSING_TIMEOUT:
            if self.coin_passage_count == 1:
                print(f"[{self.name}] SUCCESS: Exactly one coin passage detected!")
                return True
            if self.coin_passage_count > 1:
                print(f"[{self.name}] FAILURE: Multiple coins detected ({self.coin_passage_count})! Stopping motor.")
                return False
            time.sleep(0.01)

        # Handle timeout condition
        if self.coin_passage_count == 1:
            print(f"[{self.name}] SUCCESS: Exactly one coin passage detected (at timeout).")
            return True
        else:
            print(f"[{self.name}] TIMEOUT: Waited {DISPENSING_TIMEOUT}s. Found {self.coin_passage_count} passages.")
            return False

    def _dispense_single_coin_attempt(self):
        self._enable_hopper()
        # Give the motor time to spin and start dispensing
        time.sleep(0.5)  # Wait 500ms for motor to spin up
        success = self._wait_for_coin_passage()
        self._disable_hopper()
        return success

    def dispense_single_coin(self):
        """Dispense exactly one coin with retry logic."""
        if self.dispensing:
            print(f"[{self.name}] Cannot start new dispense, already in progress.")
            return False
            
        self.dispensing = True
        print(f"\n--- [{self.name}] Dispensing 1 coin ---")

        attempt = 1
        success = False
        while attempt <= MAX_RETRY_ATTEMPTS:
            print(f"[{self.name}] Attempt {attempt}/{MAX_RETRY_ATTEMPTS}...")
            if self._dispense_single_coin_attempt():
                print(f"[{self.name}] SUCCESS: Coin dispensed and verified on attempt {attempt}.")
                success = True
                break
            else:
                print(f"[{self.name}] FAILED: Attempt {attempt} was unsuccessful.")
                if self.coin_passage_count > 1:
                    print(f"[{self.name}] CRITICAL: Dispensed too many coins. Aborting.")
                    break # Don't retry if we over-dispensed
                if attempt < MAX_RETRY_ATTEMPTS:
                    print(f"[{self.name}] Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
            attempt += 1

        if not success:
            print(f"[{self.name}] CRITICAL FAILURE: Could not dispense a single coin after {MAX_RETRY_ATTEMPTS} attempts.")

        # Brief pause to allow system to settle before next command
        time.sleep(COIN_DELAY)
        self.dispensing = False
        return success

    def cleanup(self):
        if PIGPIO_AVAILABLE and self.pi and self.pi.connected:
            self._disable_hopper()
            if self.callback:
                self.callback.cancel()

class ChangeDispenser:
    """High-level manager for all hoppers."""
    def __init__(self):
        self.pi = None
        self.hoppers = {}
        self.simulated = not PIGPIO_AVAILABLE

        if not self.simulated:
            try:
                self.pi = pigpio.pi()
                if not self.pi.connected:
                    raise RuntimeError("Could not connect to pigpiod daemon.")
                
                # Create a controller for each hopper defined in config
                for name, config in HOPPER_CONFIGS.items():
                    print(f"Initializing Hopper '{name}' on Signal={config['signal_pin']}, Enable={config['enable_pin']}")
                    self.hoppers[name] = HopperController(
                        pi_instance=self.pi,
                        name=name,
                        signal_pin=config['signal_pin'],
                        enable_pin=config['enable_pin']
                    )
            except Exception as e:
                print(f"CRITICAL: Failed to initialize pigpio or hoppers: {e}. Switching to simulation mode.")
                self.simulated = True

    def dispense_change(self, amount: float, status_callback=None, admin_screen=None, database_thread_manager=None):
        """Calculates and dispenses the correct change, one coin at a time. Returns actual coins dispensed."""
        if amount <= 0:
            return {'success': True, 'coins_1': 0, 'coins_5': 0}

        num_fives = int(amount // 5)
        num_ones = int(round(amount % 5))
        
        print(f"Dispensing ₱{amount:.2f}: {num_fives}x ₱5, {num_ones}x ₱1")
        if status_callback:
            status_callback(f"Preparing to dispense ₱{amount:.2f}...")

        # Track actual coins dispensed
        actual_fives = 0
        actual_ones = 0

        # Dispense 5-peso coins
        for i in range(num_fives):
            msg = f"Dispensing ₱5 coin ({i + 1} of {num_fives})"
            if status_callback: status_callback(msg)
            print(msg)
            
            if self.simulated:
                time.sleep(1.5) # Simulate dispense time
                success = True
            else:
                success = self.hoppers['B'].dispense_single_coin()

            if success:
                actual_fives += 1
                print(f"DEBUG: Successfully dispensed ₱5 coin {actual_fives}/{num_fives}")
            else:
                error_msg = f"CRITICAL: Failed to dispense ₱5 coin {i + 1}. Dispensed {actual_fives}/{num_fives} so far."
                if status_callback: status_callback(error_msg)
                print(error_msg)
                # Continue with what we have instead of failing completely
                break

        # Dispense 1-peso coins
        for i in range(num_ones):
            msg = f"Dispensing ₱1 coin ({i + 1} of {num_ones})"
            if status_callback: status_callback(msg)
            print(msg)
            
            if self.simulated:
                time.sleep(1.5)
                success = True
            else:
                success = self.hoppers['A'].dispense_single_coin()

            if success:
                actual_ones += 1
                print(f"DEBUG: Successfully dispensed ₱1 coin {actual_ones}/{num_ones}")
            else:
                error_msg = f"CRITICAL: Failed to dispense ₱1 coin {i + 1}. Dispensed {actual_ones}/{num_ones} so far."
                if status_callback: status_callback(error_msg)
                print(error_msg)
                # Continue with what we have instead of failing completely
                break
        
        # Calculate actual change dispensed
        actual_change = (actual_fives * 5) + (actual_ones * 1)
        expected_change = (num_fives * 5) + (num_ones * 1)
        
        final_msg = f"Change dispensing complete. Dispensed ₱{actual_change:.2f} (₱{actual_fives}x5 + ₱{actual_ones}x1) of ₱{expected_change:.2f} expected."
        if status_callback: status_callback(final_msg)
        print(final_msg)
        
        return {
            'success': True,
            'coins_1': actual_ones,
            'coins_5': actual_fives,
            'actual_change': actual_change,
            'expected_change': expected_change
        }
    
    def cleanup(self):
        """Safely shut down all hoppers and the pigpio connection."""
        if self.pi and not self.simulated:
            print("Cleaning up all hopper controllers...")
            for hopper in self.hoppers.values():
                hopper.cleanup()
            self.pi.stop()
            print("pigpio connection stopped.")


class DispenseThread(QThread):
    """A dedicated thread to run the dispensing logic without freezing the GUI."""
    status_update = pyqtSignal(str)
    dispensing_finished = pyqtSignal(dict)  # Changed to emit the full result dict

    def __init__(self, dispenser: ChangeDispenser, amount: float, admin_screen=None, database_thread_manager=None):
        super().__init__()
        self.dispenser = dispenser
        self.amount = amount
        self.admin_screen = admin_screen
        self.database_thread_manager = database_thread_manager

    def run(self):
        """This method is executed when the thread starts."""
        result = self.dispenser.dispense_change(
            self.amount, 
            self.status_update.emit, 
            self.admin_screen, 
            self.database_thread_manager
        )
        self.dispensing_finished.emit(result)