from PyQt5.QtWidgets import QWidget
from .model import ThankYouModel
from .view import ThankYouScreenView

class ThankYouController(QWidget):
    """Controller for the Thank You screen - coordinates between model and view."""
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = ThankYouModel()
        self.view = ThankYouScreenView()
        
        # Set the view's layout as this controller's layout
        self.setLayout(self.view.main_layout)
        
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller ---
        self.view.finish_button_clicked.connect(self._finish_printing)
        
        # --- Model -> View ---
        self.model.status_updated.connect(self._update_status_display)
        self.model.redirect_to_idle.connect(self._go_to_idle)
    
    def _finish_printing(self):
        """Handles the finish printing action."""
        self.model.finish_printing()
    
    def _update_status_display(self, status_text, subtitle_text):
        """Updates the status display in the view."""
        status_style = self.model.get_status_style(self.model.current_state)
        self.view.update_status(status_text, subtitle_text, status_style)
    
    def _go_to_idle(self):
        """Navigates back to the idle screen."""
        print("Thank you screen: Timer expired, navigating to idle screen...")
        self.main_app.show_screen('idle')
    
    def on_enter(self):
        """Called when the screen is shown."""
        self.model.on_enter(self.main_app)
    
    def on_leave(self):
        """Called when the screen is hidden."""
        self.model.on_leave()
    
    def finish_printing(self):
        """Public method to finish printing (called by external components)."""
        self.model.finish_printing()
    
    def show_waiting_for_print(self):
        """Public method to show waiting for print status."""
        self.model.show_waiting_for_print()
    
    def show_printing_error(self, message: str):
        """Public method to show printing error."""
        self.model.show_printing_error(message)
