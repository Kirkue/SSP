# screens/usb/model.py

import os
import tempfile
import threading
from PyQt5.QtCore import QObject, pyqtSignal, QThread

try:
    from managers.usb_file_manager import USBFileManager
    USB_MANAGER_AVAILABLE = True
except ImportError:
    USB_MANAGER_AVAILABLE = False
    print("❌ Failed to import USBFileManager. Using fallback.")

class USBMonitorThread(QThread):
    """Thread for monitoring USB drive insertions and removals."""
    usb_detected = pyqtSignal(str)
    usb_removed = pyqtSignal(str)

    def __init__(self, usb_manager):
        super().__init__()
        self.usb_manager = usb_manager
        self.monitoring = True
        self._should_stop = False

    def run(self):
        print("🔄 USBMonitorThread started")
        while self.monitoring and not self._should_stop:
            try:
                new_drives, removed_drives = self.usb_manager.check_for_new_drives()
                if new_drives and self.monitoring:  # Check monitoring state before emitting
                    self.usb_detected.emit(new_drives[0])
                if removed_drives and self.monitoring:  # Check monitoring state before emitting
                    self.usb_removed.emit(removed_drives[0])
                
                # Use shorter sleep intervals and check for stop more frequently
                for _ in range(20):  # 20 * 100ms = 2 seconds total
                    if not self.monitoring or self._should_stop:
                        break
                    self.msleep(100)
                    
            except Exception as e:
                print(f"Error in USBMonitorThread: {e}")
                # Shorter error sleep too
                for _ in range(50):  # 50 * 100ms = 5 seconds total
                    if not self.monitoring or self._should_stop:
                        break
                    self.msleep(100)
        
        print("🛑 USBMonitorThread finished")

    def stop_monitoring(self):
        print("🛑 USBMonitorThread stop requested")
        self.monitoring = False
        self._should_stop = True

class USBScreenModel(QObject):
    """Handles the data and business logic for the USB screen."""
    status_changed = pyqtSignal(str, str)  # Emits status text and style key
    usb_detected = pyqtSignal(str)         # Emits USB drive path
    usb_removed = pyqtSignal(str)          # Emits removed USB drive path
    pdf_files_found = pyqtSignal(list)     # Emits list of PDF files
    show_message = pyqtSignal(str, str)    # Emits message title and text
    safety_warning = pyqtSignal(str)       # Emits safety warning message
    safety_warning_cleared = pyqtSignal()  # Emits when safety warning is cleared
    
    def __init__(self):
        super().__init__()
        self.usb_manager = self._create_usb_manager()
        self.monitoring_thread = None
        
        self.STATUS_COLORS = {
            'monitoring': '#ff9900',  # Orange
            'success': '#28a745',     # Green
            'warning': '#ffc107',     # Yellow
            'error': '#dc3545'        # Red
        }
    
    def __del__(self):
        """Destructor to ensure thread cleanup when object is destroyed."""
        self.stop_usb_monitoring()
    
    def _create_usb_manager(self):
        """Creates the USB manager instance."""
        if USB_MANAGER_AVAILABLE:
            return USBFileManager()
        else:
            # Fallback USB manager for testing
            class FallbackUSBManager:
                def __init__(self):
                    self.destination_dir = os.path.join(tempfile.gettempdir(), "PrintingSystem", "DummySession")
                    os.makedirs(self.destination_dir, exist_ok=True)
                    print(f"❗️ Using dummy USBFileManager. Destination: {self.destination_dir}")
                
                def get_usb_drives(self): 
                    return []
                
                def check_for_new_drives(self): 
                    return [], []
                
                def scan_and_copy_pdf_files(self, source_dir): 
                    return []
                
                def cleanup_all_temp_folders(self): 
                    pass
                
                def cleanup_temp_files(self): 
                    pass
            
            return FallbackUSBManager()
    
    def get_status_color(self, style_key):
        """Returns the color for a given status style."""
        return self.STATUS_COLORS.get(style_key, '#ffffff')
    
    def start_usb_monitoring(self):
        """Starts the background thread to watch for USB insertions."""
        # Ensure any existing thread is properly stopped first
        self.stop_usb_monitoring()
        
        self.status_changed.emit("Monitoring for USB devices...", 'monitoring')
        self.monitoring_thread = USBMonitorThread(self.usb_manager)
        self.monitoring_thread.usb_detected.connect(self.usb_detected.emit)
        self.monitoring_thread.usb_removed.connect(self.usb_removed.emit)
        self.monitoring_thread.start()
        print("✅ USB monitoring started")
    
    def stop_usb_monitoring(self):
        """Stops the background USB monitoring thread."""
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            print("🛑 Stopping USB monitoring thread...")
            
            # Disconnect signals first to prevent signal emission after thread stops
            try:
                self.monitoring_thread.usb_detected.disconnect()
                self.monitoring_thread.usb_removed.disconnect()
            except TypeError:
                # Signals might not be connected, ignore
                pass
            
            # Stop the monitoring loop
            self.monitoring_thread.stop_monitoring()
            
            # Wait for thread to finish gracefully
            if not self.monitoring_thread.wait(3000):  # Increased wait time to 3 seconds
                print("⚠️ Thread did not stop gracefully, terminating...")
                self.monitoring_thread.terminate()
                self.monitoring_thread.wait(1000)
            
            # Clean up thread reference
            self.monitoring_thread = None
            print("✅ USB monitoring stopped")
    
    def check_current_drives(self):
        """Checks for currently connected USB drives."""
        try:
            # Clear any existing monitoring state first
            self.stop_usb_monitoring()
            
            # Reset the USB manager's known drives to force fresh detection
            if hasattr(self.usb_manager, 'last_known_drives'):
                self.usb_manager.last_known_drives = set()
                print("🔄 Cleared USB manager's known drives cache")
            
            current_drives = self.usb_manager.get_usb_drives()
            if current_drives:
                self.handle_usb_scan_result(current_drives)
            else:
                self.start_usb_monitoring()
        except Exception as e:
            self.status_changed.emit("Error checking for USB drives.", 'error')
            print(f"Error during USB check: {e}")
    
    def force_usb_scan(self):
        """Force a comprehensive USB scan with detailed logging."""
        try:
            self.status_changed.emit("Performing comprehensive USB scan...", 'monitoring')
            
            # Stop monitoring temporarily
            self.stop_usb_monitoring()
            
            # Get all drives using multiple methods
            usb_drives = self.usb_manager.get_usb_drives()
            
            if not usb_drives:
                # Try alternative detection methods
                import psutil
                all_partitions = psutil.disk_partitions()
                print(f"All available partitions: {[(p.device, p.mountpoint, p.opts) for p in all_partitions]}")
                
                # Check for any accessible drives that might be USB
                for partition in all_partitions:
                    if partition.mountpoint and os.path.exists(partition.mountpoint):
                        try:
                            # Try to list contents to see if it's accessible
                            contents = os.listdir(partition.mountpoint)
                            print(f"Drive {partition.mountpoint} is accessible with {len(contents)} items")
                            
                            # If it's a single-letter drive (like D:, E:, F:), it might be USB
                            if len(partition.mountpoint) == 3 and partition.mountpoint.endswith('\\'):
                                drive_letter = partition.mountpoint[0]
                                if drive_letter not in ['C', 'A', 'B']:  # Exclude system drives
                                    usb_drives.append(partition.mountpoint)
                                    print(f"✅ Added potential USB drive: {partition.mountpoint}")
                        except Exception as e:
                            print(f"❌ Cannot access {partition.mountpoint}: {e}")
            
            self.handle_usb_scan_result(usb_drives)
            
        except Exception as e:
            self.status_changed.emit(f"Error during force scan: {str(e)}", 'error')
            print(f"Error during force USB scan: {e}")
    
    
    def handle_usb_scan_result(self, usb_drives):
        """Processes the results of a USB scan."""
        if not usb_drives:
            self.status_changed.emit("No USB drives found. Please insert a drive.", 'warning')
            self.start_usb_monitoring()
            return

        self.stop_usb_monitoring()
        
        if len(usb_drives) > 1:
            self.status_changed.emit(f"Found {len(usb_drives)} drives. Please connect only one.", 'error')
            return

        drive_path = usb_drives[0]
        self.status_changed.emit(f"USB drive found! Scanning for PDF files...", 'success')
        self.scan_files_from_drive(drive_path)
    
    def scan_files_from_drive(self, drive_path):
        """Scans the given drive for PDF files."""
        pdf_files = self.usb_manager.scan_and_copy_pdf_files(drive_path)
        
        if pdf_files:
            self.status_changed.emit(f"Success! Found {len(pdf_files)} PDF file(s).", 'success')
            self.pdf_files_found.emit(pdf_files)
        else:
            self.status_changed.emit("No PDF files were found on the USB drive.", 'error')
            # Restart monitoring after a delay
            threading.Timer(3.0, self.start_usb_monitoring).start()
    
    def on_usb_detected(self, drive_path):
        """Handles USB drive detection."""
        print(f"🔌 USB drive detected: {drive_path}")
        self.handle_usb_scan_result([drive_path])
    
    def on_usb_removed(self, drive_path):
        """Handles USB drive removal with safety checks."""
        print(f"🔌 USB drive removed: {drive_path}")
        
        # Check if it's safe to remove the drive
        if hasattr(self.usb_manager, 'is_drive_safe_to_remove'):
            is_safe, message = self.usb_manager.is_drive_safe_to_remove()
            if not is_safe:
                self.status_changed.emit(f"⚠️ UNSAFE REMOVAL: {message}", 'error')
                print(f"⚠️ UNSAFE USB removal detected: {message}")
                # Force safe ejection to clear any remaining operations
                if hasattr(self.usb_manager, 'force_safe_eject'):
                    self.usb_manager.force_safe_eject()
            else:
                self.status_changed.emit("USB drive was safely removed.", 'success')
        else:
            self.status_changed.emit("USB drive was removed.", 'warning')
        
        self.start_usb_monitoring()
    
    def check_disk_safety(self):
        """Check if the current USB drive is safe to remove."""
        if hasattr(self.usb_manager, 'get_safety_warning'):
            warning = self.usb_manager.get_safety_warning()
            if warning:
                self.safety_warning.emit(warning)
                return False
            else:
                self.safety_warning_cleared.emit()
        return True
    
    def reset_usb_state(self):
        """Completely reset USB monitoring state - useful when switching drives."""
        print("🔄 Resetting USB monitoring state...")
        
        # Stop any existing monitoring
        self.stop_usb_monitoring()
        
        # Clear USB manager's cache
        if hasattr(self.usb_manager, 'last_known_drives'):
            self.usb_manager.last_known_drives = set()
            print("🔄 Cleared USB manager's known drives cache")
        
        # Reset status
        self.status_changed.emit("Ready for USB device...", 'monitoring')
        
        print("✅ USB state reset complete")
