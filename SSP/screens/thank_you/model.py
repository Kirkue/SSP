from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import threading

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
        self.print_job_started = False
        
    def _on_timer_timeout(self):
        """Called when the redirect timer expires."""
        print("Thank you screen: Timer timeout triggered, emitting redirect signal...")
        self.redirect_to_idle.emit()
        
    def on_enter(self, main_app):
        """Called when the screen is shown."""
        self.main_app = main_app
        
        # Check if print job has already been started to prevent duplicates
        if self.print_job_started:
            print("Thank you screen: Print job already started, skipping duplicate start")
            return
        
        self.current_state = "waiting"
        self.status_updated.emit(
            "PRINTING IN PROGRESS...",
            "Please wait while your document is being printed."
        )
        self.redirect_timer.stop()
        
        # Connect to printer manager signals to monitor print completion
        if hasattr(main_app, 'printer_manager'):
            print("Thank you screen: Connecting to printer manager signals...")
            print("Thank you screen: Connecting print_job_successful signal...")
            main_app.printer_manager.print_job_successful.connect(self._on_print_success)
            print("Thank you screen: Connecting print_job_failed signal...")
            main_app.printer_manager.print_job_failed.connect(self._on_print_failed)
            print("Thank you screen: Printer signals connected successfully")
            
            # Test signal connection
            print("Thank you screen: Testing signal connection...")
            try:
                main_app.printer_manager.print_job_successful.emit()
                print("Thank you screen: Test signal emitted")
            except Exception as e:
                print(f"Thank you screen: Error emitting test signal: {e}")
            
            # Start the print job
            self._start_print_job(main_app)
            
            # Start a safety timeout in case signals don't work (2 minutes)
            self.redirect_timer.start(120000)  # 2 minute safety timeout
            print("Thank you screen: Safety timeout started (2 minutes)")
        else:
            print("Thank you screen: ERROR - No printer manager found!")
            # Fallback: start timer if no printer manager
            self.redirect_timer.start(10000)  # 10 second fallback
    
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
    
    def _on_print_success(self):
        """Handles successful print completion."""
        print("=" * 60)
        print("Thank you screen: _on_print_success called - Print job completed successfully")
        print("Thank you screen: Current thread:", threading.current_thread().name)
        print("=" * 60)
        
        # Stop the safety timeout since we got the success signal
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
            print("Thank you screen: Safety timeout cancelled")
        
        self.current_state = "completed"
        self.status_updated.emit(
            "PRINTING COMPLETED",
            "Kindly collect your documents. We hope to see you again!"
        )
        
        # Start the 5-second timer to go back to the idle screen
        print("Thank you screen: Starting 5-second redirect timer...")
        self.redirect_timer.start(5000)
    
    def _start_print_job(self, main_app):
        """Start the print job using stored print job details."""
        if hasattr(main_app, 'current_print_job') and main_app.current_print_job:
            print("Thank you screen: Starting print job with stored details...")
            print(f"Thank you screen: Print job details: {main_app.current_print_job}")
            
            try:
                main_app.printer_manager.print_file(
                    file_path=main_app.current_print_job['file_path'],
                    selected_pages=main_app.current_print_job['selected_pages'],
                    copies=main_app.current_print_job['copies'],
                    color_mode=main_app.current_print_job['color_mode']
                )
                print("Thank you screen: Print job started successfully")
                self.print_job_started = True  # Mark that print job has been started
            except Exception as e:
                print(f"Thank you screen: Error starting print job: {e}")
                self.show_printing_error(f"Failed to start print job: {e}")
        else:
            print("Thank you screen: No print job details found")
            self.show_printing_error("No print job details available")
    
    def _on_print_failed(self, error_message):
        """Handles print job failure."""
        print(f"Thank you screen: Print job failed: {error_message}")
        self.show_printing_error(error_message)
    
    def on_leave(self):
        """Called when the screen is hidden."""
        # Disconnect printer signals to prevent memory leaks
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'printer_manager'):
            try:
                self.main_app.printer_manager.print_job_successful.disconnect(self._on_print_success)
                self.main_app.printer_manager.print_job_failed.disconnect(self._on_print_failed)
                print("Thank you screen: Printer signals disconnected")
            except:
                pass  # Ignore errors if signals weren't connected
        
        # Stop the timer if the user navigates away manually
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
        
        # Reset the print job started flag for next transaction
        self.print_job_started = False
        print("Thank you screen: Print job flag reset for next transaction")
    
    def get_status_style(self, state):
        """Returns the appropriate style for the status label based on state."""
        styles = {
            "printing": "color: #36454F; font-size: 42px; font-weight: bold;",
            "waiting": "color: #ffc107; font-size: 42px; font-weight: bold;",  # Yellow
            "completed": "color: #28a745; font-size: 42px; font-weight: bold;",  # Green
            "error": "color: #dc3545; font-size: 42px; font-weight: bold;"  # Red
        }
        return styles.get(state, styles["printing"])
