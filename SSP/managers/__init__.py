# managers/__init__.py

# Import managers directly - they should not have circular dependencies
try:
    from .printer_manager import PrinterManager
except ImportError as e:
    print(f"Warning: Could not import PrinterManager: {e}")
    PrinterManager = None

try:
    from .hopper_manager import HopperController, ChangeDispenser, DispenseThread, PIGPIO_AVAILABLE
except ImportError as e:
    print(f"Warning: Could not import hopper_manager classes: {e}")
    HopperController = None
    ChangeDispenser = None
    DispenseThread = None
    PIGPIO_AVAILABLE = False

try:
    from .sms_manager import get_sms_manager
except ImportError as e:
    print(f"Warning: Could not import get_sms_manager: {e}")
    get_sms_manager = None

try:
    from .usb_file_manager import USBFileManager
except ImportError as e:
    print(f"Warning: Could not import USBFileManager: {e}")
    USBFileManager = None

__all__ = [
    'PrinterManager',
    'HopperController',
    'ChangeDispenser',
    'DispenseThread',
    'PIGPIO_AVAILABLE',
    'get_sms_manager',
    'USBFileManager'
]
