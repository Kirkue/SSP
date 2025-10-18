# screens/idle/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QDialog
from PyQt5.QtCore import Qt

from .model import IdleModel
from .view import IdleScreenView
from screens.dialogs.pin_dialog import PinDialogController as PinDialog

# Import GPIO functionality for manual acceptor control
try:
    import pigpio
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

class IdleController(QWidget):
    """Manages the Idle screen's logic and UI."""
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = IdleModel()
        self.view = IdleScreenView()
        
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)
        
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller ---
        self.view.screen_touched.connect(self._handle_screen_touch)
        self.view.admin_button_clicked.connect(self._go_to_admin)
        
        # --- Model -> View ---
        self.model.background_image_loaded.connect(self.view.set_background_image)
        self.model.show_message.connect(self._show_message)
    
    def _handle_screen_touch(self, event):
        """Handles screen touch events."""
        admin_button_geometry = self.view.get_admin_button_geometry()
        
        if self.model.validate_touch_interaction(event.pos(), admin_button_geometry):
            self._start_printing()
    
    def _start_printing(self):
        """Starts the printing process by navigating to USB screen."""
        self.main_app.show_screen('usb')
    
    def _go_to_admin(self):
        """Opens PIN dialog and navigates to admin screen if PIN is correct."""
        dialog = PinDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.main_app.show_screen('admin')
        else:
            print("PIN Dialog closed without correct PIN.")
    
    def _show_message(self, title, text):
        """Shows a message to the user."""
        print(f"{title}: {text}")
    
    def _disable_acceptors(self):
        """Manually disable coin and bill acceptors to ensure they are turned off."""
        print("IDLE: Manually disabling acceptors...")
        
        if not GPIO_AVAILABLE:
            print("IDLE: GPIO not available - acceptors disabled (simulation mode)")
            return
        
        try:
            # Create a temporary GPIO connection for manual control
            pi = pigpio.pi()
            if not pi.connected:
                print("IDLE: Could not connect to pigpio daemon")
                return
            
            # GPIO pin definitions (matching persistent GPIO)
            COIN_INHIBIT_PIN = 22  # Coin acceptor inhibit pin
            BILL_INHIBIT_PIN = 23   # Bill acceptor inhibit pin
            
            # Disable coin acceptor (HIGH = enabled, LOW = disabled)
            pi.set_mode(COIN_INHIBIT_PIN, pigpio.OUTPUT)
            pi.write(COIN_INHIBIT_PIN, 0)  # LOW = disabled
            print("IDLE: Coin acceptor disabled")
            
            # Disable bill acceptor (LOW = enabled, HIGH = disabled)  
            pi.set_mode(BILL_INHIBIT_PIN, pigpio.OUTPUT)
            pi.write(BILL_INHIBIT_PIN, 1)  # HIGH = disabled
            print("IDLE: Bill acceptor disabled")
            
            # Small delay to ensure state change
            import time
            time.sleep(0.1)
            
            # Clean up the temporary connection
            pi.stop()
            print("IDLE: Acceptors manually disabled successfully")
            
        except Exception as e:
            print(f"IDLE: Error manually disabling acceptors: {e}")
            # Try to clean up even if there was an error
            try:
                if 'pi' in locals():
                    pi.stop()
            except:
                pass
    
    # --- Public API for main_app ---
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Idle screen entered.")
        
        # Manually disable acceptors to ensure they are turned off
        self._disable_acceptors()
        
        # Check paper count before allowing normal operation
        if self.main_app.check_paper_count_and_redirect():
            return  # Redirected to no paper screen, don't proceed with normal idle operations
        
        # The model will automatically load the background image
    
    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Idle screen left.")
        # Ensure acceptors are still disabled when leaving idle screen
        self._disable_acceptors()
