# Hopper GPIO Noise Filtering Fixes

## Problem
The hopper sensors were detecting false triggers with very short pulses (0.000s), causing continuous "False trigger (pulse too short)" messages. This was due to electrical noise and insufficient debouncing.

## Root Cause
1. **Insufficient debouncing**: 10ms minimum was too short for electrical noise
2. **No cooldown period**: Rapid callbacks from electrical interference
3. **Sensors always active**: Continuous monitoring caused more false triggers
4. **No hardware filtering**: Missing GPIO glitch filter
5. **No maximum time filter**: Could detect stuck sensors

## Fixes Applied

### 1. Enhanced Software Debouncing
```python
def _sensor_callback(self, gpio, level, tick):
    # Add cooldown period to prevent rapid false triggers
    if hasattr(self, 'last_callback_time'):
        time_since_last = pigpio.tickDiff(self.last_callback_time, current_time) / 1000000.0
        if time_since_last < 0.05:  # 50ms cooldown between callbacks
            return
    
    # Increased debounce time and added maximum time filter
    if 0.05 <= elapsed <= 2.0:  # Valid coin passage: 50ms to 2 seconds
        # Valid coin detection
    elif elapsed < 0.05:
        print(f"False trigger (pulse too short: {elapsed:.3f}s) - ignored")
    else:
        print(f"False trigger (pulse too long: {elapsed:.3f}s) - ignored")
```

**Improvements:**
- ✅ **5x longer debounce time** (10ms → 50ms)
- ✅ **Added cooldown period** (50ms between callbacks)
- ✅ **Added maximum time filter** (2 seconds)
- ✅ **Better false trigger detection**

### 2. Hardware Debouncing
```python
# Add hardware debouncing by setting GPIO glitch filter
self.pi.set_glitch_filter(self.signal_pin, 10000)  # 10ms hardware debounce
```

**Improvements:**
- ✅ **Hardware glitch filter** (10ms)
- ✅ **Pull-up resistor enabled**
- ✅ **Proper GPIO mode setup**

### 3. Sensor Management
```python
def disable_sensor(self):
    """Temporarily disable sensor to reduce false triggers."""
    if self.callback:
        self.callback.cancel()
        self.callback = None

def enable_sensor(self):
    """Re-enable sensor for coin detection."""
    if self.pi and self.pi.connected and not self.callback:
        self.callback = self.pi.callback(self.signal_pin, pigpio.EITHER_EDGE, self._sensor_callback)
```

**Improvements:**
- ✅ **Sensors disabled by default**
- ✅ **Enabled only when dispensing**
- ✅ **Disabled immediately after dispensing**
- ✅ **Reduces false triggers significantly**

### 4. Smart Dispensing Logic
```python
# Enable sensor for this hopper only when dispensing
self.hoppers['A'].enable_sensor()
success = self.hoppers['A'].dispense_single_coin()
# Disable sensor after dispensing to reduce false triggers
self.hoppers['A'].disable_sensor()
```

**Improvements:**
- ✅ **Sensors active only when needed**
- ✅ **Immediate disable after dispensing**
- ✅ **Better power management**
- ✅ **Reduced electrical noise**

## Noise Filtering Strategy

### 🔧 **Multi-Layer Filtering**
1. **Hardware Level**: GPIO glitch filter (10ms)
2. **Software Level**: Callback cooldown (50ms)
3. **Logic Level**: Pulse duration filtering (50ms - 2s)
4. **System Level**: Sensor enable/disable control

### 📱 **Smart Sensor Management**
- **Idle State**: Sensors disabled (no false triggers)
- **Dispensing State**: Sensors enabled only for active hopper
- **Post-Dispensing**: Sensors immediately disabled
- **Error State**: Sensors disabled for safety

### 🛡️ **False Trigger Prevention**
- **Electrical Noise**: Hardware + software filtering
- **Rapid Callbacks**: Cooldown period
- **Short Pulses**: Minimum time filter
- **Stuck Sensors**: Maximum time filter
- **Continuous Monitoring**: Sensor enable/disable

## Expected Behavior

### ✅ **Before Fixes (Problematic)**
```
[A] SENSOR: Coin entering sensor
[A] SENSOR: False trigger (pulse too short: 0.000s)
[A] SENSOR: Coin entering sensor
[A] SENSOR: False trigger (pulse too short: 0.000s)
[A] SENSOR: Coin entering sensor
[A] SENSOR: False trigger (pulse too short: 0.000s)
```

### ✅ **After Fixes (Improved)**
```
Initializing Hopper 'A' on Signal=21, Enable=16
[A] Cleaned up existing callbacks on pin 21
[A] GPIO setup completed successfully
Disabling hopper sensors to reduce false triggers...
[A] Sensor disabled to reduce false triggers
```

### ✅ **During Dispensing (Controlled)**
```
Dispensing ₱1 coin (1 of 2)
[A] Sensor re-enabled for coin detection
[A] SENSOR: Coin entering sensor
[A] SENSOR: Coin passage complete (took 0.150s)
[A] Sensor disabled to reduce false triggers
```

## Testing

### Test Script: `test_hopper_noise_filtering.py`
Run this script to verify the noise filtering improvements:

```bash
python3 test_hopper_noise_filtering.py
```

**This script tests:**
1. ✅ Debouncing improvements
2. ✅ Hardware debouncing features
3. ✅ Sensor management strategy
4. ✅ Noise sources and solutions
5. ✅ False trigger prevention
6. ✅ Expected behavior
7. ✅ Troubleshooting guidance

## Files Modified

1. **`managers/hopper_manager.py`**
   - Enhanced `_sensor_callback()` with better debouncing
   - Added `disable_sensor()` and `enable_sensor()` methods
   - Added hardware glitch filter
   - Modified dispensing logic to enable/disable sensors
   - Added callback cooldown period
   - Added pulse duration filtering

2. **`test_hopper_noise_filtering.py`** (New)
   - Comprehensive noise filtering testing
   - Debouncing improvement verification
   - Sensor management testing
   - Troubleshooting guidance

## Verification

After applying these fixes, the system should:

1. **Have no false triggers when idle** ✅
2. **Show clean startup without noise** ✅
3. **Only activate sensors when dispensing** ✅
4. **Properly detect coins during dispensing** ✅
5. **Disable sensors immediately after dispensing** ✅
6. **Handle electrical noise much better** ✅
7. **Provide clear debugging information** ✅

## Troubleshooting

### If you still see false triggers:
1. **Check wiring connections** - Loose connections cause noise
2. **Verify power supply stability** - Voltage ripple affects sensors
3. **Check for electromagnetic interference** - Motors, power supplies
4. **Consider external pull-up resistors** - Stronger signal
5. **Check GPIO pin assignments** - Avoid noisy pins
6. **Add external RC filter** - Hardware noise filtering
7. **Use shielded cables** - Reduce interference
8. **Check ground connections** - Proper grounding

### Additional improvements if needed:
- Increase glitch filter time (20ms, 50ms)
- Add external RC filter circuit
- Use opto-isolators for sensor signals
- Implement software-based noise filtering
- Add sensor calibration routines

The hopper system will now have much better noise filtering and should eliminate the false trigger messages you were seeing.
