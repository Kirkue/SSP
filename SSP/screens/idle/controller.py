# screens/idle/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QDialog
from PyQt5.QtCore import Qt

from .model import IdleModel
from .view import IdleScreenView
from screens.dialogs.pin_dialog import PinDialogController as PinDialog

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
    
    # --- Public API for main_app ---
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Idle screen entered.")
        
        # Check paper count before allowing normal operation
        if self.main_app.check_paper_count_and_redirect():
            return  # Redirected to no paper screen, don't proceed with normal idle operations
        
        # The model will automatically load the background image
    
    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Idle screen left.")
