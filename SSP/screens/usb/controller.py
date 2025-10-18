# screens/usb/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QMessageBox
from PyQt5.QtCore import QTimer

from .model import USBScreenModel
from .view import USBScreenView

class USBController(QWidget):
    """Manages the USB screen's logic and UI."""
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = USBScreenModel()
        self.view = USBScreenView()
        
        # Setup timeout timer (1 minute = 60000ms)
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)
        
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller ---
        self.view.back_button_clicked.connect(self._go_back)
        # Reset timeout on user interaction
        self.view.back_button_clicked.connect(self._reset_timeout)
        
        # --- Model -> View ---
        self.model.status_changed.connect(self._update_status)
        self.model.usb_detected.connect(self.model.on_usb_detected)
        self.model.usb_removed.connect(self.model.on_usb_removed)
        self.model.pdf_files_found.connect(self._handle_pdf_files_found)
        self.model.show_message.connect(self.view.show_message)
        
        # Safety warning connections
        self.model.safety_warning.connect(self.view.show_safety_warning)
        self.model.safety_warning_cleared.connect(self.view.hide_safety_warning)
    
    def _update_status(self, text, style_key):
        """Updates the status indicator with the given text and style."""
        color_hex = self.model.get_status_color(style_key)
        self.view.update_status_indicator(text, style_key, color_hex)
    
    
    def _handle_pdf_files_found(self, pdf_files):
        """Handles when PDF files are found on the USB drive."""
        self.main_app.file_browser_screen.load_pdf_files(pdf_files)
        self.main_app.show_screen('file_browser')
    
    def _go_back(self):
        """Navigates back to the idle screen."""
        self.main_app.show_screen('idle')
    
    # --- Public API for main_app ---
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("🔄 Entering USB screen, performing initial check...")
        self.view.start_blinking()
        
        # Reset the returning flag when entering normally
        self.model.set_returning_from_file_browser(False)
        
        # Reset USB manager state for new session
        self.model.reset_usb_manager_state()
        
        self.model.check_current_drives()
        
        # Start timeout timer (1 minute)
        self.timeout_timer.start(60000)
        print("⏰ USB screen timeout started (1 minute)")
    
    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("⏹️ Leaving USB screen")
        self.model.stop_usb_monitoring()
        self.view.stop_blinking()
        
        # Stop timeout timer
        self.timeout_timer.stop()
    
    def _on_timeout(self):
        """Handle timeout - return to idle screen."""
        print("⏰ USB screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
    
    def _reset_timeout(self):
        """Reset the timeout timer (call on user activity)."""
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        print("⏰ USB screen timeout reset")
    
    def reset_usb_state(self):
        """Public method to reset USB monitoring state."""
        self.model.reset_usb_state()