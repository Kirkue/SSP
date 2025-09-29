# -*- coding: utf-8 -*-
import pigpio
import time
import select
import sys

# --- General Configuration ---
COIN_DELAY = 1           # Delay after a successful dispense before being ready again
DISPENSING_TIMEOUT = 10  # Maximum time to wait for a single coin
MAX_RETRY_ATTEMPTS = 5   # Maximum attempts per coin before giving up
RETRY_DELAY = 0.5        # Delay between retry attempts

### NEW: Centralized configuration for multiple hoppers ###
HOPPER_CONFIGS = {
    'A': {
        'signal_pin': 21,  # Coin pulse input for Hopper A
        'enable_pin': 16   # Hopper enable control for Hopper A
    },
    'B': {
        'signal_pin': 6,   # Coin pulse input for Hopper B
        'enable_pin': 26   # Hopper enable control for Hopper B
    }
}


class HopperController:
    ### MODIFIED: __init__ now accepts pins and a name to be generic ###
    def __init__(self, pi_instance, name, signal_pin, enable_pin):
        self.pi = pi_instance
        if not self.pi.connected:
            raise Exception("Failed to connect to pigpiod")

        # Hopper-specific identifiers
        self.name = name
        self.signal_pin = signal_pin
        self.enable_pin = enable_pin

        # State variables
        self.enabled = False
        self.dispensing = False

        # Sensor state tracking
        self.sensor_active = False
        self.coin_passage_detected = False
        self.coin_passage_count = 0
        self.last_sensor_change = 0

        # Setup GPIO
        self.pi.set_mode(self.signal_pin, pigpio.INPUT)
        self.pi.set_pull_up_down(self.signal_pin, pigpio.PUD_UP)
        self.pi.set_mode(self.enable_pin, pigpio.OUTPUT)

        # Monitor both rising and falling edges to track coin passage
        # Each instance will have its own callback tied to its specific signal pin
        self.callback = self.pi.callback(self.signal_pin, pigpio.EITHER_EDGE, self._sensor_callback)

        # Start with hopper disabled
        self._disable_hopper()

    def _enable_hopper(self):
        self.pi.write(self.enable_pin, 0)  # Active low
        self.enabled = True
        print(f"[{self.name}] Hopper motor ENABLED")

    def _disable_hopper(self):
        self.pi.write(self.enable_pin, 1)  # Inactive high
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
        """Single attempt to dispense exactly one coin."""
        # Enable hopper motor
        self._enable_hopper()

        # Wait for exactly one coin passage
        success = self._wait_for_coin_passage()

        # Stop motor immediately after detection (success or failure)
        self._disable_hopper()

        return success
        print(f"[{self.name}] Hopper motor DISABLED")
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

    def test_sensor(self):
        """Test the sensor by monitoring its state."""
        print(f"\n--- [{self.name}] Testing Sensor ---")
        print("Drop a coin manually through the sensor. Press Enter to stop.")
        
        last_state = self.pi.read(self.signal_pin)
        print(f"Initial sensor state: {'HIGH (clear)' if last_state == 1 else 'LOW (blocked)'}")

        while True:
            # Check for user input to stop
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                # Clear the input buffer
                sys.stdin.readline()
                break
            
            # The callback handles printing the state changes automatically
            time.sleep(0.1)
        
        print(f"--- [{self.name}] Sensor test finished ---")


    def stop(self):
        """Emergency stop."""
        self._disable_hopper()
        self.dispensing = False
        print(f"[{self.name}] EMERGENCY STOP: Hopper stopped.")

    def cleanup(self):
        """Clean shutdown for this specific hopper instance."""
        print(f"[{self.name}] Cleaning up...")
        self.stop()
        if self.callback:
            self.callback.cancel()

# --- Main execution ---
if __name__ == "__main__":
    hoppers = {}
    pi = None
    
    try:
        # ### NEW: Initialize pigpio once ###
        pi = pigpio.pi()
        if not pi.connected:
            raise RuntimeError("Could not connect to pigpiod. Is the daemon running?")

        # ### NEW: Create a HopperController instance for each configured hopper ###
        for name, config in HOPPER_CONFIGS.items():
            print(f"Initializing Hopper '{name}' on Signal={config['signal_pin']}, Enable={config['enable_pin']}")
            hoppers[name] = HopperController(
                pi_instance=pi,
                name=name,
                signal_pin=config['signal_pin'],
                enable_pin=config['enable_pin']
            )
        
        print("\n=== Multi-Hopper Controller ===")
        hopper_keys = "/".join(hoppers.keys())
        print("Commands:")
        print(f"  '{hopper_keys}'         - Dispense one coin from the specified hopper (e.g., 'a')")
        print(f"  'test {hopper_keys}'    - Test a hopper's sensor (e.g., 'test b')")
        print(f"  'stop {hopper_keys}'    - Emergency stop a specific hopper (e.g., 'stop a')")
        print("  'stop all'  - Stop all hoppers")
        print("  'q'         - Quit")

        while True:
            command_str = input("\nEnter command: ").strip().lower()
            if not command_str:
                continue

            parts = command_str.split()
            cmd = parts[0]
            target = parts[1].upper() if len(parts) > 1 else None

            if cmd == 'q':
                break
            
            # Commands that target a specific hopper
            if target in hoppers:
                hopper = hoppers[target]
                if cmd == 'test':
                    hopper.test_sensor()
                elif cmd == 'stop':
                    hopper.stop()
                else: # Default action is dispense
                    if cmd.upper() == target:
                         hopper.dispense_single_coin()
                    else:
                        print(f"Unknown command '{cmd}' for hopper '{target}'. Did you mean just '{target}'?")
            # Commands that don't need a specific target or have a special one
            elif cmd == 'stop' and target == 'ALL':
                print("Stopping all hoppers...")
                for h in hoppers.values():
                    h.stop()
            elif cmd.upper() in hoppers: # Handle single-letter dispense command
                hoppers[cmd.upper()].dispense_single_coin()
            else:
                print(f"Invalid command or unknown hopper. Valid hoppers: {list(hoppers.keys())}")


    except KeyboardInterrupt:
        print("\nShutting down due to Ctrl+C...")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        if hoppers:
            print("Cleaning up all hoppers...")
            for hopper in hoppers.values():
                hopper.cleanup()
        if pi and pi.connected:
            print("Stopping pigpio connection.")
            pi.stop()
        print("Shutdown complete.")
