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

from ui.theme import COLORS, FONT


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
        print("DEBUG: Thank you screen on_enter called")
        self.main_app = main_app

        # Prevent duplicate print job starts
        if self.print_job_started:
            print("DEBUG: Print job already started, skipping")
            return

        # Check if there's a valid print job to start
        if not hasattr(main_app, 'current_print_job') or not main_app.current_print_job:
            print("DEBUG: No valid print job available, skipping print start")
            return

        # Set initial state
        self.current_state = "waiting"
        self.status_updated.emit(
            "Thank you for printing with us",
            "You may now remove your USB."
        )
        self.redirect_timer.stop()

        # Hide admin override button when starting new print job
        self.admin_override_hidden.emit()

        # Connect to printer manager signals
        if hasattr(main_app, 'printer_manager'):
            print("DEBUG: Connecting to printer manager signals")
            try:
                main_app.printer_manager.print_job_successful.connect(self._on_print_success)
                main_app.printer_manager.print_job_failed.connect(self._on_print_failed)
                print("DEBUG: Printer signals connected successfully")
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
            "Thank you for printing with us",
            "Kindly collect your documents. We hope to see you again!"
        )

        # Start 5-second timer before returning to idle
        self.redirect_timer.start(5000)

    def show_waiting_for_print(self):
        """Update state to show that print job is in progress."""
        self.current_state = "waiting"
        self.status_updated.emit(
            "Thank you for printing with us",
            "Your document is being processed."
        )

    def show_printing_error(self, message: str):
        """
        Update state to show a printing error.

        Args:
            message: Error message from printer manager
        """
        self.current_state = "error"

        # Stop any existing safety timeout since we're now in error state
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()

        # Check if this is a paper jam error
        is_paper_jam = "paper jam" in message.lower() or "jam" in message.lower()

        # Sanitize common verbose CUPS errors for better UX
        if "client-error-document-format-not-supported" in message:
            clean_message = "Document format is not supported by the printer."
        elif "CUPS Error" in message:
            clean_message = "Could not communicate with the printer."
        elif is_paper_jam:
            clean_message = "Paper jam detected. Please clear the paper jam."
        elif "paused" in message.lower():
            clean_message = "The printer is paused."
        else:
            clean_message = "An error occurred."

        self.error_type = "paper_jam" if is_paper_jam else "printing_error"

        self.status_updated.emit(
            "ERROR OCCURRED",
            f"Error: {clean_message}\nPlease contact an administrator."
        )

        # SMS notification disabled for print job failures (not critical enough)
        # Only log to database for tracking
        print(f"⚠️ Print job failure (SMS disabled): {clean_message}")

        # Log error to database
        try:
            from utils.error_logger import log_error
            log_error("Printing Error", message, "thank_you_screen")
        except Exception as db_error:
            print(f"⚠️ Failed to log error to database: {db_error}")

        # Show admin override button
        self.admin_override_requested.emit()

    def show_no_paper_error(self, paper_count: int):
        """
        Update state to show a no paper error.

        Args:
            paper_count: Current paper count (0 to 3: the kiosk closes at 3 sheets or fewer)
        """
        self.current_state = "error"
        self.error_type = "no_paper"

        # The counter is software: it doesn't notice the tray being refilled, so the kiosk stays
        # closed until an admin records the refill. Say so, or loading paper looks like it did nothing.
        admin_hint = (
            "\n\nAdmin: after loading paper, tap Admin Override and record it with Refill "
            "(or the + button) under Paper Count. The kiosk stays closed until then."
        )

        # Stop any existing safety timeout since we're now in error state
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()

        if paper_count == 0:
            self.status_updated.emit(
                "NO PAPER AVAILABLE",
                "The printer is out of paper. Please contact an administrator to refill paper."
                + admin_hint
            )
        else:
            pages = f"Only {paper_count} page{'s' if paper_count != 1 else ''} remaining."
            self.status_updated.emit(
                "LOW PAPER WARNING",
                f"{pages} Please contact an administrator to refill paper." + admin_hint
            )

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

        # Stop any existing safety timeout since we're now in error state
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()

        self.status_updated.emit(
            "PAPER JAM DETECTED",
            "Paper jam detected. Please clear the paper jam and try again.\nContact an administrator if needed."
        )

        # Show admin override button
        self.admin_override_requested.emit()

    def handle_admin_override(self):
        """Handle admin override - navigates to admin screen."""
        self.current_state = "admin_override"
        self.status_updated.emit(
            "ADMIN OVERRIDE",
            "Navigating to admin screen..."
        )
        # Hide admin override button since override is being processed
        self.admin_override_hidden.emit()
        # Navigate directly to admin screen
        if hasattr(self, 'main_app') and self.main_app:
            self.main_app.show_screen('admin')

    def _on_print_success(self):
        """Handle successful print completion."""
        # Stop all timers since we got the success signal
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()

        if hasattr(self, 'warning_timer') and self.warning_timer.isActive():
            self.warning_timer.stop()

        # Hide admin override button since print succeeded
        self.admin_override_hidden.emit()

        # Clean up temporary files after successful printing
        self._cleanup_temp_files()

        # Update state
        self.current_state = "completed"
        self.status_updated.emit(
            "Thank you for printing with us",
            "Kindly collect your documents. We hope to see you again!"
        )

        # Start 5-second redirect timer
        self.redirect_timer.start(5000)

    def _cleanup_temp_files(self):
        """Clean up temporary files after successful printing."""
        try:
            print("🧹 Cleaning up temporary files after printing...")

            # Import USBFileManager to access cleanup methods
            try:
                from managers.usb_file_manager import USBFileManager

                # Create a temporary USB manager instance to access cleanup methods
                temp_usb_manager = USBFileManager()

                # Clean up all temp folders from previous sessions
                if hasattr(temp_usb_manager, 'cleanup_all_temp_folders'):
                    temp_usb_manager.cleanup_all_temp_folders()
                    print("✅ Cleaned up all temporary folders")
                else:
                    print("⚠️ cleanup_all_temp_folders method not available")

            except ImportError as e:
                print(f"⚠️ Could not import USBFileManager: {e}")
            except Exception as e:
                print(f"⚠️ Error during temp file cleanup: {e}")

        except Exception as e:
            print(f"⚠️ Error during temp file cleanup: {e}")

    def _start_print_job(self, main_app):
        """
        Start the print job using stored print job details.

        Args:
            main_app: Main application window with current_print_job attribute
        """
        print("DEBUG: _start_print_job called")
        print(f"DEBUG: main_app has current_print_job: {hasattr(main_app, 'current_print_job')}")
        if hasattr(main_app, 'current_print_job'):
            print(f"DEBUG: current_print_job value: {main_app.current_print_job}")
        else:
            print("DEBUG: current_print_job attribute does not exist")
            print(f"DEBUG: main_app attributes: {[attr for attr in dir(main_app) if not attr.startswith('_')]}")

        if hasattr(main_app, 'current_print_job') and main_app.current_print_job:
            try:
                print(f"DEBUG: Starting print job with details: {main_app.current_print_job}")
                main_app.printer_manager.print_file(
                    file_path=main_app.current_print_job['file_path'],
                    selected_pages=main_app.current_print_job['selected_pages'],
                    copies=main_app.current_print_job['copies'],
                    color_mode=main_app.current_print_job['color_mode']
                )
                self.print_job_started = True
                print("DEBUG: Print job started successfully")
            except Exception as e:
                print(f"❌ Error starting print job: {e}")
                self.show_printing_error(f"Failed to start print job: {e}")
        else:
            print("DEBUG: No print job details available")
            self.show_printing_error("No print job details available")

    def _start_timers(self):
        """Start monitoring timers in the main thread."""
        # Only start safety timeout if not in error state
        # Error states should wait for admin override, not auto-redirect
        if self.current_state not in ["error", "admin_override"]:
            # Start safety timeout (2 minutes) only for non-error states
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
            except Exception:
                pass

        # Stop timers
        if self.redirect_timer.isActive():
            self.redirect_timer.stop()

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
        base = f"font-size: {FONT['size_display']}px; font-weight: 700;"
        color_by_state = {
            "printing": COLORS["text"],
            "waiting": COLORS["warning"],
            "completed": COLORS["success"],
            "error": COLORS["danger"],
        }
        color = color_by_state.get(state, color_by_state["printing"])
        return f"color: {color}; {base}"
