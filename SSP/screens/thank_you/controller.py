from PyQt5.QtWidgets import QWidget, QDialog
from .model import ThankYouModel
from .view import ThankYouScreenView
from screens.dialogs.pin_dialog import PinDialogController as PinDialog

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
        self.view.admin_override_clicked.connect(self._handle_admin_override)
        
        # --- Model -> View ---
        self.model.status_updated.connect(self._update_status_display)
        self.model.redirect_to_idle.connect(self._go_to_idle)
        self.model.admin_override_requested.connect(self._show_admin_override_button)
        self.model.admin_override_hidden.connect(self._hide_admin_override_button)
    
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
    
    def show_paper_jam_error(self, message: str):
        """Public method to show paper jam error specifically."""
        self.model.show_paper_jam_error(message)
    
    def show_no_paper_error(self, paper_count: int):
        """Public method to show no paper error."""
        self.model.show_no_paper_error(paper_count)
    
    def _show_admin_override_button(self):
        """Shows the admin override button when an error occurs."""
        print("Thank you screen: Showing admin override button")
        self.view.show_admin_override_button()
    
    def _hide_admin_override_button(self):
        """Hides the admin override button when error is resolved."""
        print("Thank you screen: Hiding admin override button")
        self.view.hide_admin_override_button()
    
    def _handle_admin_override(self):
        """Handles admin override button click - shows PIN dialog."""
        print("Thank you screen: Admin override button clicked")
        dialog = PinDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            print("Thank you screen: PIN accepted, processing admin override")
            self.model.handle_admin_override()
        else:
            print("Thank you screen: PIN dialog cancelled or failed")
