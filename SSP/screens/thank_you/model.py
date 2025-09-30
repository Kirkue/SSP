from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import threading
import subprocess
import time

class ThankYouModel(QObject):
    """Model for the Thank You screen - handles business logic and state management."""
    
    # Signals for UI updates
    status_updated = pyqtSignal(str, str)  # status_text, subtitle_text
    redirect_to_idle = pyqtSignal()
    admin_override_requested = pyqtSignal()  # request to show admin override button
    
    def __init__(self):
        super().__init__()
        self.redirect_timer = QTimer()
        self.redirect_timer.setSingleShot(True)
        self.redirect_timer.timeout.connect(self._on_timer_timeout)
        
        # Screen states
        self.current_state = "initial"
        self.print_job_started = False
        
        # Add a periodic check timer for debugging
        self.status_check_timer = QTimer()
        self.status_check_timer.timeout.connect(self._check_print_status)
        self.status_check_timer.setSingleShot(False)
        
    def _on_timer_timeout(self):
        """Called when the redirect timer expires."""
        print("Thank you screen: Timer timeout triggered, emitting redirect signal...")
        self.redirect_to_idle.emit()
        
    def on_enter(self, main_app):
        """Called when the screen is shown."""
        print("=" * 60)
        print("Thank you screen: on_enter() called")
        print("Thank you screen: main_app type:", type(main_app).__name__)
        print("Thank you screen: print_job_started flag:", self.print_job_started)
        print("=" * 60)
        
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
        
        # Start the print job and monitor both signals and printer status
        if hasattr(main_app, 'printer_manager'):
            print("Thank you screen: Starting print job...")
            print("Thank you screen: Checking for current_print_job...")
            if hasattr(main_app, 'current_print_job'):
                print("Thank you screen: current_print_job found:", main_app.current_print_job)
            else:
                print("Thank you screen: ERROR - No current_print_job found!")
            
            # Connect to printer signals as primary method
            print("Thank you screen: Connecting to printer signals...")
            try:
                main_app.printer_manager.print_job_successful.connect(self._on_print_success)
                print("Thank you screen: print_job_successful signal connected")
                main_app.printer_manager.print_job_failed.connect(self._on_print_failed)
                print("Thank you screen: print_job_failed signal connected")
                print("Thank you screen: Printer signals connected successfully")
            except Exception as e:
                print(f"Thank you screen: Error connecting signals: {e}")
                import traceback
                traceback.print_exc()
            
            # Start the print job
            print("Thank you screen: About to call _start_print_job...")
            self._start_print_job(main_app)
            print("Thank you screen: _start_print_job completed")
            
            # Start timers using QTimer.singleShot to ensure they run in main thread
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._start_timers)
            print("Thank you screen: Timer start queued for main thread")
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
        
        # Show admin override button and don't auto-redirect
        self.admin_override_requested.emit()
        
        # Don't start automatic redirect timer for errors - wait for admin override
    
    def handle_admin_override(self):
        """Handles admin override - allows going back to idle screen."""
        print("Thank you screen: Admin override requested")
        self.current_state = "admin_override"
        self.status_updated.emit(
            "ADMIN OVERRIDE",
            "Returning to idle screen..."
        )
        # Start a short timer to show the message before redirecting
        self.redirect_timer.start(2000)
    
    def _show_printing_warning(self):
        """Shows a warning if printing is taking too long."""
        if self.current_state == "waiting":
            print("Thank you screen: Printing is taking longer than expected")
            self.status_updated.emit(
                "PRINTING IN PROGRESS...",
                "Printing is taking longer than usual. Please wait..."
            )
    
    def _on_print_success(self):
        """Handles successful print completion with enhanced verification."""
        print("=" * 60)
        print("Thank you screen: _on_print_success called - Print job completed successfully")
        print("Thank you screen: Current thread:", threading.current_thread().name)
        print("=" * 60)
        
        # Stop all timers since we got the success signal
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
            print("Thank you screen: Safety timeout cancelled")
        
        if hasattr(self, 'warning_timer') and self.warning_timer.isActive():
            self.warning_timer.stop()
            print("Thank you screen: Warning timer cancelled")
        
        if self.status_check_timer.isActive():
            self.status_check_timer.stop()
            print("Thank you screen: Status check timer cancelled")
        
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
        print("Thank you screen: _start_print_job called")
        
        if hasattr(main_app, 'current_print_job') and main_app.current_print_job:
            print("Thank you screen: Starting print job with stored details...")
            print(f"Thank you screen: Print job details: {main_app.current_print_job}")
            
            try:
                print("Thank you screen: About to call printer_manager.print_file...")
                main_app.printer_manager.print_file(
                    file_path=main_app.current_print_job['file_path'],
                    selected_pages=main_app.current_print_job['selected_pages'],
                    copies=main_app.current_print_job['copies'],
                    color_mode=main_app.current_print_job['color_mode']
                )
                print("Thank you screen: Print job started successfully")
                self.print_job_started = True  # Mark that print job has been started
                print("Thank you screen: print_job_started flag set to True")
            except Exception as e:
                print(f"Thank you screen: Error starting print job: {e}")
                import traceback
                traceback.print_exc()
                self.show_printing_error(f"Failed to start print job: {e}")
        else:
            print("Thank you screen: No print job details found")
            self.show_printing_error("No print job details available")
    
    def _check_print_status(self):
        """Simplified printer status checking as fallback."""
        # Only check if we're still waiting (signal not received)
        if self.current_state != "waiting":
            return
            
        print("Thank you screen: Fallback - Checking printer status...")
        
        try:
            # Check if printer is idle using lpstat command
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                # Parse the output to see if printer is idle
                output = result.stdout.lower()
                if 'idle' in output or 'ready' in output:
                    print("Thank you screen: Fallback - Printer is idle, print job completed")
                    print("Thank you screen: Signal not received, using fallback method")
                    self._on_print_success()
                else:
                    print("Thank you screen: Fallback - Printer is still busy")
            else:
                print(f"Thank you screen: Fallback - lpstat failed with return code {result.returncode}")
                print(f"Thank you screen: Error output: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("Thank you screen: Fallback - lpstat command timed out")
        except Exception as e:
            print(f"Thank you screen: Fallback - Error checking printer status: {e}")
    
    def _start_timers(self):
        """Start the timers in the main thread with enhanced monitoring."""
        print("Thank you screen: Starting enhanced timers in main thread...")
        
        # Start periodic printer status check as fallback (every 10 seconds)
        self.status_check_timer.start(10000)  # Check every 10 seconds (back to original)
        print("Thank you screen: Printer status check started as fallback (every 10 seconds)")
        
        # Start a safety timeout in case both methods fail (2 minutes)
        self.redirect_timer.start(120000)  # 2 minute safety timeout (back to original)
        print("Thank you screen: Safety timeout started (2 minutes)")
    
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
        
        # Stop the timers if the user navigates away manually
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
        if self.status_check_timer.isActive():
            self.status_check_timer.stop()
            print("Thank you screen: Status check timer stopped")
        
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
