"""
Thank You Screen Model

Business logic for the Thank You screen shown after payment completion.
Manages print job status updates, displays appropriate messages, and handles
screen redirection timing.

States:
- initial: Screen first shown
- waiting: Print job in progress
- completed: Print job finished successfully
- error: Print job failed (paper jam or other error)
- admin_override: Admin manually overriding error state
"""

from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import threading
import subprocess


class ThankYouModel(QObject):
    """
    Model for the Thank You screen.
    
    Manages state, print job monitoring, and coordinates with the printer manager
    to display appropriate status messages to users.
    
    Signals:
        status_updated(str, str): Emits (status_text, subtitle_text) for UI updates
        redirect_to_idle: Emitted when it's time to return to idle screen
        admin_override_requested: Emitted to show admin override button on errors
    """
    
    status_updated = pyqtSignal(str, str)
    redirect_to_idle = pyqtSignal()
    admin_override_requested = pyqtSignal()
    admin_override_hidden = pyqtSignal()
    
    def __init__(self):
        """Initialize the Thank You model."""
        super().__init__()
        
        # Redirect timer for auto-navigation back to idle
        self.redirect_timer = QTimer()
        self.redirect_timer.setSingleShot(True)
        self.redirect_timer.timeout.connect(self._on_timer_timeout)
        
        # Status check timer for fallback monitoring
        self.status_check_timer = QTimer()
        self.status_check_timer.timeout.connect(self._check_print_status)
        self.status_check_timer.setSingleShot(False)
        
        # Screen state tracking
        self.current_state = "initial"
        self.print_job_started = False
        self.error_type = None
        
    def _on_timer_timeout(self):
        """Handle redirect timer timeout."""
        self.redirect_to_idle.emit()
        
    def on_enter(self, main_app):
        """
        Called when the screen is shown.
        
        Connects to printer signals and starts the print job if not already started.
        
        Args:
            main_app: Reference to main application window
        """
        self.main_app = main_app
        
        # Prevent duplicate print job starts
        if self.print_job_started:
            return
        
        # Set initial state
        self.current_state = "waiting"
        self.status_updated.emit(
            "PRINTING IN PROGRESS...",
            "Please wait while your document is being printed."
        )
        self.redirect_timer.stop()
        
        # Hide admin override button when starting new print job
        self.admin_override_hidden.emit()
        
        # Connect to printer manager signals
        if hasattr(main_app, 'printer_manager'):
            try:
                main_app.printer_manager.print_job_successful.connect(self._on_print_success)
                main_app.printer_manager.print_job_failed.connect(self._on_print_failed)
            except Exception as e:
                print(f"❌ Error connecting printer signals: {e}")
            
            # Start print job
            self._start_print_job(main_app)
            
            # Start monitoring timers
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self._start_timers)
        else:
            print("❌ No printer manager found")
            self.redirect_timer.start(10000)
    
    def finish_printing(self):
        """
        Update state to show print completion.
        
        Called when print job completes successfully. Starts 5-second timer
        before redirecting to idle screen.
        """
        self.current_state = "completed"
        self.status_updated.emit(
            "PRINTING COMPLETED",
            "Kindly collect your documents. We hope to see you again!"
        )
        
        # Start 5-second timer before returning to idle
        self.redirect_timer.start(5000)
    
    def show_waiting_for_print(self):
        """Update state to show that print job is in progress."""
        self.current_state = "waiting"
        self.status_updated.emit(
            "PRINTING IN PROGRESS...",
            "Please wait while your document is being printed."
        )
    
    def show_printing_error(self, message: str):
        """
        Update state to show a printing error.
        
        Args:
            message: Error message from printer manager
        """
        self.current_state = "error"
        
        # Check if this is a paper jam error
        is_paper_jam = "paper jam" in message.lower() or "jam" in message.lower()
        
        # Sanitize common verbose CUPS errors for better UX
        if "client-error-document-format-not-supported" in message:
            clean_message = "Document format is not supported by the printer."
        elif "CUPS Error" in message:
            clean_message = "Could not communicate with the printer."
        elif is_paper_jam:
            clean_message = "Paper jam detected. Please clear the paper jam."
        else:
            clean_message = "An unknown printing error occurred."
        
        self.error_type = "paper_jam" if is_paper_jam else "printing_error"
        
        self.status_updated.emit(
            "PRINTING FAILED",
            f"Error: {clean_message}\nPlease contact an administrator."
        )
        
        # Send SMS notification (backup method)
        try:
            from managers.sms_manager import send_printing_error_sms
            send_printing_error_sms(message)
        except Exception as sms_error:
            print(f"⚠️ Failed to send SMS notification: {sms_error}")
        
        # Show admin override button
        self.admin_override_requested.emit()
    
    def show_paper_jam_error(self, message: str):
        """
        Update state to show a paper jam error specifically.
        
        Args:
            message: Paper jam error message
        """
        self.current_state = "error"
        self.error_type = "paper_jam"
        
        self.status_updated.emit(
            "PAPER JAM DETECTED",
            "Paper jam detected. Please clear the paper jam and try again.\nContact an administrator if needed."
        )
        
        # Show admin override button
        self.admin_override_requested.emit()
    
    def handle_admin_override(self):
        """Handle admin override - allows going back to idle screen."""
        self.current_state = "admin_override"
        self.status_updated.emit(
            "ADMIN OVERRIDE",
            "Returning to idle screen..."
        )
        # Hide admin override button since override is being processed
        self.admin_override_hidden.emit()
        # Short timer before redirecting
        self.redirect_timer.start(2000)
    
    def _on_print_success(self):
        """Handle successful print completion."""
        # Stop all timers since we got the success signal
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
        
        if hasattr(self, 'warning_timer') and self.warning_timer.isActive():
            self.warning_timer.stop()
        
        if self.status_check_timer.isActive():
            self.status_check_timer.stop()
        
        # Hide admin override button since print succeeded
        self.admin_override_hidden.emit()
        
        # Update state
        self.current_state = "completed"
        self.status_updated.emit(
            "PRINTING COMPLETED",
            "Kindly collect your documents. We hope to see you again!"
        )
        
        # Start 5-second redirect timer
        self.redirect_timer.start(5000)
    
    def _start_print_job(self, main_app):
        """
        Start the print job using stored print job details.
        
        Args:
            main_app: Main application window with current_print_job attribute
        """
        if hasattr(main_app, 'current_print_job') and main_app.current_print_job:
            try:
                main_app.printer_manager.print_file(
                    file_path=main_app.current_print_job['file_path'],
                    selected_pages=main_app.current_print_job['selected_pages'],
                    copies=main_app.current_print_job['copies'],
                    color_mode=main_app.current_print_job['color_mode']
                )
                self.print_job_started = True
            except Exception as e:
                print(f"❌ Error starting print job: {e}")
                self.show_printing_error(f"Failed to start print job: {e}")
        else:
            self.show_printing_error("No print job details available")
    
    def _check_print_status(self):
        """
        Fallback method to check printer status if signals fail.
        
        Uses lpstat command to check if printer is idle/ready as a backup
        method in case print completion signals don't arrive.
        Improved to handle multiple printers and detect active printer completion.
        """
        # Only check if we're still waiting
        if self.current_state != "waiting":
            return
        
        try:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                output = result.stdout
                output_lower = output.lower()
                
                # Check printer status using alerts-based detection (fallback method)
                target_printer = "HP_Smart_Tank_580_590_series_5E0E1D_USB"
                is_printing = False
                
                detailed_result = subprocess.run(['lpstat', '-l', '-p', target_printer], 
                                               capture_output=True, text=True, timeout=5)
                
                if detailed_result.returncode == 0:
                    # Look for alerts line in the output
                    for line in detailed_result.stdout.split('\n'):
                        line = line.strip()
                        if line.startswith("Alerts:"):
                            alerts_text = line.replace("Alerts:", "").strip()
                            print(f"Fallback: Printer alerts for {target_printer}: {alerts_text}")
                            
                            if alerts_text and alerts_text != "none":
                                alerts_found = [alert.strip() for alert in alerts_text.split()]
                                
                                # Check if printer is actively printing
                                if "cups-waiting-for-job-completed" in alerts_found:
                                    is_printing = True
                                    print(f"Fallback: Printer '{target_printer}' still processing/printing (cups-waiting-for-job-completed)")
                                
                                # Check for specific error conditions
                                if "media-jam-error" in alerts_found or "paper-jam" in alerts_found:
                                    self.show_paper_jam_error(f"Paper jam detected on {target_printer}")
                                    return
                                elif "media-empty-error" in alerts_found or "media-needed-error" in alerts_found:
                                    self.show_printing_error(f"No paper detected on {target_printer}")
                                    return
                                elif "offline" in alerts_found or "stopped" in alerts_found:
                                    self.show_printing_error(f"Printer {target_printer} went offline")
                                    return
                                elif "error" in alerts_found:
                                    self.show_printing_error(f"Printer error on {target_printer}")
                                    return
                            else:
                                # No alerts means printer is idle
                                print(f"Fallback: Printer '{target_printer}' is idle (no alerts)")
                            break
                
                # Only assume completion if target printer is not actively printing
                if not is_printing:
                    print("Fallback: Target printer not actively printing, marking print as complete")
                    self._on_print_success()
                else:
                    print(f"Fallback: Still waiting for target printer '{target_printer}' to finish printing")
                    
        except subprocess.TimeoutExpired:
            print("⚠️ Fallback lpstat command timed out")
        except Exception as e:
            print(f"⚠️ Fallback status check error: {e}")
    
    def _start_timers(self):
        """Start monitoring timers in the main thread."""
        # Start periodic printer status check as fallback (every 5 seconds)
        self.status_check_timer.start(5000)
        
        # Start safety timeout (2 minutes)
        self.redirect_timer.start(120000)
    
    def _on_print_failed(self, error_message):
        """
        Handle print job failure.
        
        Args:
            error_message: Error description from printer manager
        """
        print(f"❌ Print job failed: {error_message}")
        self.show_printing_error(error_message)
    
    def on_leave(self):
        """Called when the screen is hidden - cleanup connections and timers."""
        # Disconnect printer signals
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'printer_manager'):
            try:
                self.main_app.printer_manager.print_job_successful.disconnect(self._on_print_success)
                self.main_app.printer_manager.print_job_failed.disconnect(self._on_print_failed)
            except:
                pass
        
        # Stop timers
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()
        if self.status_check_timer.isActive():
            self.status_check_timer.stop()
        
        # Reset state for next transaction
        self.print_job_started = False
    
    def get_status_style(self, state):
        """
        Get CSS style for status label based on state.
        
        Args:
            state: Current screen state
            
        Returns:
            CSS style string for status label
        """
        styles = {
            "printing": "color: #36454F; font-size: 42px; font-weight: bold;",
            "waiting": "color: #ffc107; font-size: 42px; font-weight: bold;",
            "completed": "color: #28a745; font-size: 42px; font-weight: bold;",
            "error": "color: #dc3545; font-size: 42px; font-weight: bold;"
        }
        return styles.get(state, styles["printing"])
