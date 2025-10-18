# screens/idle/model.py

from PyQt5.QtCore import QObject, pyqtSignal
import os

class IdleModel(QObject):
    """Handles the data and business logic for the idle screen."""
    background_image_loaded = pyqtSignal(str)  # Emits image path when loaded
    show_message = pyqtSignal(str, str)        # Emits message title and text
    
    def __init__(self):
        super().__init__()
        self.background_image_path = None
        self._load_background_image()
    
    def _load_background_image(self):
        """Loads the background image path and emits signal."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        image_path = os.path.join(base_dir, 'assets', 'idle_screen background.png')
        
        if os.path.exists(image_path):
            self.background_image_path = image_path
            self.background_image_loaded.emit(image_path)
        else:
            print(f"WARNING: Background image not found at '{image_path}'.")
            self.show_message.emit("Warning", f"Background image not found at '{image_path}'.")
    
    def get_background_image_path(self):
        """Returns the background image path."""
        return self.background_image_path
    
    def validate_touch_interaction(self, event_pos, admin_button_geometry):
        """Validates if the touch interaction should start printing or not."""
        # If the touch is on the admin button, don't start printing
        if admin_button_geometry and admin_button_geometry.contains(event_pos):
            return False
        return True
