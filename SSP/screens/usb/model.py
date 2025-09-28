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

    def run(self):
        while self.monitoring:
            try:
                new_drives, removed_drives = self.usb_manager.check_for_new_drives()
                if new_drives:
                    self.usb_detected.emit(new_drives[0])
                if removed_drives:
                    self.usb_removed.emit(removed_drives[0])
                self.msleep(2000)
            except Exception as e:
                print(f"Error in USBMonitorThread: {e}")
                self.msleep(5000)

    def stop_monitoring(self):
        self.monitoring = False

class USBScreenModel(QObject):
    """Handles the data and business logic for the USB screen."""
    status_changed = pyqtSignal(str, str)  # Emits status text and style key
    usb_detected = pyqtSignal(str)         # Emits USB drive path
    usb_removed = pyqtSignal(str)          # Emits removed USB drive path
    pdf_files_found = pyqtSignal(list)     # Emits list of PDF files
    show_message = pyqtSignal(str, str)    # Emits message title and text
    
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
        if not self.monitoring_thread or not self.monitoring_thread.isRunning():
            self.status_changed.emit("Monitoring for USB devices...", 'monitoring')
            self.monitoring_thread = USBMonitorThread(self.usb_manager)
            self.monitoring_thread.usb_detected.connect(self.usb_detected.emit)
            self.monitoring_thread.usb_removed.connect(self.usb_removed.emit)
            self.monitoring_thread.start()
            print("✅ USB monitoring started")
    
    def stop_usb_monitoring(self):
        """Stops the background USB monitoring thread."""
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            self.monitoring_thread.stop_monitoring()
            self.monitoring_thread.wait(2000)
            self.monitoring_thread = None
            print("✅ USB monitoring stopped")
    
    def check_current_drives(self):
        """Checks for currently connected USB drives."""
        try:
            current_drives = self.usb_manager.get_usb_drives()
            if current_drives:
                self.handle_usb_scan_result(current_drives)
            else:
                self.start_usb_monitoring()
        except Exception as e:
            self.status_changed.emit("Error checking for USB drives.", 'error')
            print(f"Error during USB check: {e}")
    
    
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
    
    def create_test_files(self):
        """Creates dummy PDF files for testing purposes."""
        print("\n=== TEST: Simulating PDF files found ===")
        temp_dir = self.usb_manager.destination_dir
        dummy_files = []
        
        try:
            for i, name in enumerate(["report.pdf", "presentation_notes.pdf"]):
                path = os.path.join(temp_dir, name)
                with open(path, 'wb') as f:
                    f.write(b"%PDF-1.4\n1 0 obj<</Type/Page>>endobj\nxref\n0 2\n0000000000 65535 f \n0000000009 00000 n \ntrailer<</Size 2/Root 1 0 R>>\nstartxref\n24\n%%EOF")
                dummy_files.append({
                    'filename': name, 
                    'size': 1024 * (50+i*20), 
                    'pages': i + 2, 
                    'path': path, 
                    'type': '.pdf'
                })
            
            self.status_changed.emit(f"Success! Found {len(dummy_files)} PDF file(s).", 'success')
            self.pdf_files_found.emit(dummy_files)
            
        except Exception as e:
            self.show_message.emit("Test Error", f"Failed to create dummy files: {e}")
    
    
    def on_usb_detected(self, drive_path):
        """Handles USB drive detection."""
        print(f"🔌 USB drive detected: {drive_path}")
        self.handle_usb_scan_result([drive_path])
    
    def on_usb_removed(self, drive_path):
        """Handles USB drive removal."""
        print(f"🔌 USB drive removed: {drive_path}")
        self.status_changed.emit("USB drive was removed.", 'warning')
        self.start_usb_monitoring()
