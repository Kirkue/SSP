from PyQt5.QtCore import QObject, pyqtSignal, QTimer

class ThankYouModel(QObject):
    """Model for the Thank You screen - handles business logic and state management."""
    
    # Signals for UI updates
    status_updated = pyqtSignal(str, str)  # status_text, subtitle_text
    redirect_to_idle = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.redirect_timer = QTimer()
        self.redirect_timer.setSingleShot(True)
        self.redirect_timer.timeout.connect(self._on_timer_timeout)
        
        # Screen states
        self.current_state = "initial"
        
    def _on_timer_timeout(self):
        """Called when the redirect timer expires."""
        print("Thank you screen: Timer timeout triggered, emitting redirect signal...")
        self.redirect_to_idle.emit()
        
    def on_enter(self, main_app):
        """Called when the screen is shown."""
        self.current_state = "printing"
        self.status_updated.emit(
            "SENDING TO PRINTER...",
            "Please wait while we process your print job."
        )
        self.redirect_timer.stop()
        
        # Check if there's already a print job running
        if hasattr(main_app, 'printer_manager') and main_app.printer_manager.print_thread:
            print("Thank you screen: Print job already in progress")
        else:
            print("Thank you screen: No print job detected, this might be an error")
    
    def finish_printing(self):
        """Updates the state to finished and starts the timer to go idle."""
        print("Thank you screen: Finishing printing, starting 5-second timer")
        self.current_state = "completed"
        self.status_updated.emit(
            "PRINTING COMPLETED",
            "Kindly collect your documents. We hope to see you again!"
        )
        
        # Start the 5-second timer to go back to the idle screen
        print("Thank you screen: Starting 5-second redirect timer...")
        self.redirect_timer.start(5000)
    
    def show_waiting_for_print(self):
        """Updates the state to show that we're waiting for the actual printing to complete."""
        print("Thank you screen: Showing waiting for print status")
        self.current_state = "waiting"
        self.status_updated.emit(
            "PRINTING IN PROGRESS...",
            "Please wait while your document is being printed."
        )
    
    def show_printing_error(self, message: str):
        """Updates the state to show a printing error."""
        self.current_state = "error"
        
        # Sanitize common, verbose CUPS errors for a better user display
        if "client-error-document-format-not-supported" in message:
            clean_message = "Document format is not supported by the printer."
        elif "CUPS Error" in message:
            clean_message = "Could not communicate with the printer."
        else:
            clean_message = "An unknown printing error occurred."
        
        self.status_updated.emit(
            "PRINTING FAILED",
            f"Error: {clean_message}\nPlease contact an administrator."
        )
        
        # Start a longer timer to allow the user to read the error
        self.redirect_timer.start(15000)
    
    def on_leave(self):
        """Called when the screen is hidden."""
        # Stop the timer if the user navigates away manually
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
    
    def get_status_style(self, state):
        """Returns the appropriate style for the status label based on state."""
        styles = {
            "printing": "color: #36454F; font-size: 42px; font-weight: bold;",
            "waiting": "color: #ffc107; font-size: 42px; font-weight: bold;",  # Yellow
            "completed": "color: #28a745; font-size: 42px; font-weight: bold;",  # Green
            "error": "color: #dc3545; font-size: 42px; font-weight: bold;"  # Red
        }
        return styles.get(state, styles["printing"])
