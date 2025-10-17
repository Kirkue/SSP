"""
Self-Service Printing System - Main Application

This module serves as the entry point for the SSP (Self-Service Printer) application.
It manages the main window, screen navigation, and coordinates between various managers
including printer, database, and ink analysis operations.

Key Components:
- PrintingSystemApp: Main application window with stacked screen management
- Screen Controllers: Idle, USB, File Browser, Print Options, Payment, Admin, Data Viewer, Thank You
- Managers: PrinterManager, DatabaseThreadManager, InkAnalysisThreadManager
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QDesktopWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from screens.idle import IdleController
from screens.usb import USBController
from screens.file_browser import FileBrowserController
from screens.payment import PaymentController
from screens.print_options import PrintOptionsController
from screens.admin import AdminController
from screens.data_viewer import DataViewerController
from screens.thank_you import ThankYouController
from database.models import init_db
from managers.printer_manager import PrinterManager
from managers.db_threader import DatabaseThreadManager
from managers.ink_analysis_threader import InkAnalysisThreadManager
from managers.sms_manager import cleanup_sms
from managers.persistent_gpio import cleanup_persistent_gpio
from config import get_config

try:
    from managers.usb_file_manager import USBFileManager
except Exception as e:
    print(f"❌ Failed to import USBFileManager: {e}")


class PrintingSystemApp(QMainWindow):
    """
    Main application window for the Self-Service Printing System.
    
    Manages screen navigation, printer operations, and coordinates between
    various subsystems including payment processing, ink analysis, and database operations.
    
    Attributes:
        stacked_widget: Container for all application screens
        printer_manager: Handles print job execution and monitoring
        db_threader: Manages database operations in background thread
        ink_analysis_threader: Manages ink usage analysis in background thread
    """
    
    # Screen index mapping for stacked widget navigation
    SCREEN_MAP = {
        'idle': 0,
        'usb': 1,
        'file_browser': 2,
        'printing_options': 3,
        'payment': 4,
        'admin': 5,
        'data_viewer': 6,
        'thank_you': 7
    }
    
    def __init__(self):
        """Initialize the main application window and all subsystems."""
        super().__init__()
        self.setWindowTitle("Printing System GUI")
        
        # Get screen dimensions and set appropriate window size
        self._setup_display()

        # Initialize stacked widget for screen management
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Initialize all screen controllers
        self.idle_screen = IdleController(self)
        self.usb_screen = USBController(self)
        self.file_browser_screen = FileBrowserController(self)
        self.printing_options_screen = PrintOptionsController(self)
        self.payment_screen = PaymentController(self)
        self.admin_screen = AdminController(self)
        
        # Initialize thread managers for background operations
        self.db_threader = DatabaseThreadManager()
        self.ink_analysis_threader = InkAnalysisThreadManager()
        self.db_threader.start()
        self.ink_analysis_threader.start()
        
        # Connect thread managers for real-time data updates
        self._connect_thread_managers()
        
        # Initialize printer manager (no dependencies)
        self.printer_manager = PrinterManager()
        
        # Initialize remaining screens that depend on other components
        try:
            print("🔄 Initializing data viewer screen...")
            self.data_viewer_screen = DataViewerController(self, self.admin_screen.db_manager)
            print("✅ Data viewer screen initialized successfully")
        except Exception as e:
            print(f"❌ ERROR: Failed to initialize data viewer screen: {e}")
            # Create a dummy data viewer to prevent crashes
            self.data_viewer_screen = None
            
        self.thank_you_screen = ThankYouController(self)

        # Add all screens to stacked widget in order (see SCREEN_MAP)
        self.stacked_widget.addWidget(self.idle_screen)
        self.stacked_widget.addWidget(self.usb_screen)
        self.stacked_widget.addWidget(self.file_browser_screen)
        self.stacked_widget.addWidget(self.printing_options_screen)
        self.stacked_widget.addWidget(self.payment_screen)
        self.stacked_widget.addWidget(self.admin_screen)
        
        # Only add data viewer if it was initialized successfully
        if self.data_viewer_screen is not None:
            self.stacked_widget.addWidget(self.data_viewer_screen)
        else:
            print("⚠️ Data viewer screen not available - skipping")
            
        self.stacked_widget.addWidget(self.thank_you_screen)

        # Show idle screen as initial screen
        self.show_screen('idle')

        # Apply application-wide styles
        self.setStyleSheet("""
            QMainWindow {
                background-color: transparent;
            }
        """)
    
    def _setup_display(self):
        """
        Configure display settings - keep original resolution but go fullscreen.
        """
        # Set the original window size
        self.setGeometry(100, 100, 1280, 720)
        self.setMinimumSize(1280, 720)
        
        # Set window flags for kiosk-like behavior
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        
        # Go fullscreen on startup
        print("🖥️ Starting in fullscreen mode")
        self.showFullScreen()
    
    def _connect_thread_managers(self):
        """
        Connect signals between thread managers and application components.
        
        Sets up signal connections for:
        - Ink analysis completion and CMYK level updates
        - Payment completion to trigger printing
        - Print job status updates (success, failure, waiting)
        """
        # Connect ink analysis completion for database updates
        self.ink_analysis_threader.analysis_completed.connect(self._on_ink_analysis_completed)
        
        # Connect payment and printing signals (will be connected after screens are initialized)
        # This connection happens after all screens are created to avoid AttributeErrors
    
    def _on_ink_analysis_completed(self, result):
        """
        Handle ink analysis completion and forward CMYK level updates.
        
        Args:
            result: Dictionary containing analysis results with keys:
                - database_updated: Boolean indicating if DB was updated
                - cmyk_levels: Dictionary with C, M, Y, K percentages
        """
        if result.get('database_updated', False) and 'cmyk_levels' in result:
            print(f"CMYK levels updated: {result['cmyk_levels']}")
            self.db_threader.cmyk_levels_updated.emit(result['cmyk_levels'])

        # Connect payment and printing signals after screens are ready
        self.payment_screen.payment_completed.connect(self.on_payment_completed)
        self.printer_manager.print_job_successful.connect(self.on_print_successful)
        self.printer_manager.print_job_failed.connect(self.on_print_failed)
        self.printer_manager.print_job_waiting.connect(self.on_print_waiting)

    def check_paper_count_and_redirect(self):
        """
        Check current paper count and redirect to error screen if needed.
        
        Returns:
            bool: True if redirected to error screen, False if paper is available
        """
        paper_count = self.admin_screen.get_paper_count()
        if paper_count <= 1:
            print(f"⚠️ Low paper detected: {paper_count} pages remaining. Redirecting to error screen.")
            self.show_screen('thank_you')
            # Show the no paper error on the thank you screen
            self.thank_you_screen.show_no_paper_error(paper_count)
            return True
        return False

    def show_screen(self, screen_name):
        """
        Navigate to a different screen by name.
        
        Properly handles screen lifecycle by calling on_leave() on the current screen
        and on_enter() on the new screen if those methods exist.
        
        Args:
            screen_name: String name of the screen to show (see SCREEN_MAP)
        """
        if screen_name not in self.SCREEN_MAP:
            print(f"❌ ERROR: Unknown screen name: {screen_name}")
            return

        # Call on_leave lifecycle method for current screen
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, 'on_leave'):
            current_widget.on_leave()

        # Switch to the new screen
        target_index = self.SCREEN_MAP[screen_name]
        self.stacked_widget.setCurrentIndex(target_index)
        
        # Call on_enter lifecycle method for new screen
        new_widget = self.stacked_widget.currentWidget()
        if hasattr(new_widget, 'on_enter'):
            new_widget.on_enter()

    def on_payment_completed(self, payment_info):
        """
        Handle successful payment and initiate print job.
        
        This is called after payment is processed and change is dispensed.
        The screen transition to thank_you is handled by the payment dialog.
        
        Args:
            payment_info: Dictionary containing:
                - pdf_data: Dict with 'path' and 'filename'
                - copies: Number of copies to print
                - color_mode: 'Color' or 'Black and White'
                - selected_pages: List of page numbers to print
        """
        print(f"Payment completed. Starting print job for {payment_info['pdf_data']['filename']}")
        
        # Check paper count before starting print job
        if self.check_paper_count_and_redirect():
            print("❌ Cannot proceed with print job - insufficient paper")
            return
        
        self.printer_manager.print_file(
            file_path=payment_info['pdf_data']['path'],
            copies=payment_info['copies'],
            color_mode=payment_info['color_mode'],
            selected_pages=payment_info['selected_pages']
        )

    def on_print_successful(self):
        """
        Handle successful print job completion.
        
        Triggers ink analysis and updates the thank you screen to show completion status.
        If not currently on the thank you screen, navigates to it first.
        """
        print("✅ Print job successfully completed")
        
        # Trigger ink analysis for the printed job (if print job info available)
        self._trigger_ink_analysis()
        
        current_screen = self.stacked_widget.currentWidget()
        
        if current_screen == self.thank_you_screen:
            self.thank_you_screen.finish_printing()
        else:
            # Print job completed but we're on wrong screen - navigate first
            print(f"⚠️ Print completed on wrong screen ({type(current_screen).__name__}), navigating to thank you screen")
            self.show_screen('thank_you')
            QTimer.singleShot(100, lambda: self.thank_you_screen.finish_printing())
    
    def _trigger_ink_analysis(self):
        """
        Trigger ink usage analysis for the completed print job.
        
        Uses the temporary PDF created by the printer (which contains only
        the selected pages that were actually printed). This ensures ink
        analysis works even if the USB drive is removed.
        
        After analysis completes, the temporary PDF is cleaned up.
        """
        if not hasattr(self, 'current_print_job') or not self.current_print_job:
            print("⚠️ No print job info available for ink analysis")
            return
        
        # Get the temp PDF path from printer manager
        if not hasattr(self.printer_manager, 'last_temp_pdf_path') or not self.printer_manager.last_temp_pdf_path:
            print("⚠️ No temp PDF available for ink analysis")
            return
        
        temp_pdf_path = self.printer_manager.last_temp_pdf_path
        
        try:
            # Use temp PDF (already has only selected pages!) instead of original file
            # This works even if USB drive is removed
            self.ink_analysis_threader.analyze_and_update(
                pdf_path=temp_pdf_path,
                selected_pages=None,  # All pages in temp PDF (already filtered)
                copies=self.current_print_job['copies'],
                dpi=150,
                color_mode=self.current_print_job['color_mode'],
                callback=self._on_ink_analysis_completed
            )
        except Exception as e:
            print(f"⚠️ Error triggering ink analysis: {e}")
            # Clean up temp PDF even if analysis fails
            self.printer_manager.cleanup_last_temp_pdf()
    
    def _on_ink_analysis_completed(self, operation):
        """
        Handle ink analysis completion and clean up temporary PDF.
        
        Args:
            operation: InkAnalysisOperation object with result or error
        """
        if operation.error:
            print(f"⚠️ Ink analysis failed: {operation.error}")
        else:
            result = operation.result
            if result.get('success', False) and result.get('database_updated', False):
                print("✅ Ink levels updated in database")
        
        # Always clean up temp PDF after analysis completes
        self.printer_manager.cleanup_last_temp_pdf()

    def on_print_waiting(self):
        """
        Handle print job waiting state.
        
        Called when the print job has been sent to CUPS and we're waiting
        for the actual printing to complete. Updates the thank you screen
        to show "Printing in Progress" status.
        """
        print("⏳ Waiting for print job to complete")
        
        if self.stacked_widget.currentWidget() == self.thank_you_screen:
            self.thank_you_screen.show_waiting_for_print()
        else:
            print(f"⚠️ Print waiting signal on wrong screen ({type(self.stacked_widget.currentWidget()).__name__})")

    def on_print_failed(self, error_message):
        """
        Handle print job failure.
        
        Sends SMS notification for print failures, logs to database, and displays appropriate
        error message on the thank you screen. Distinguishes between paper
        jam errors and general printing errors.
        
        Args:
            error_message: String describing the error that occurred
        """
        print(f"❌ Print job failed: {error_message}")
        
        # Send SMS notification for all print failures
        try:
            from managers.sms_manager import send_printing_error_sms
            send_printing_error_sms(error_message)
        except Exception as sms_error:
            print(f"⚠️ Failed to send SMS notification: {sms_error}")
        
        # Log error to database
        try:
            from utils.error_logger import log_error
            log_error("Print Job Failed", error_message, "main_app")
        except Exception as db_error:
            print(f"⚠️ Failed to log error to database: {db_error}")
        
        # Display error on thank you screen
        if self.stacked_widget.currentWidget() == self.thank_you_screen:
            # Check if this is a paper jam error for specialized handling
            if "paper jam" in error_message.lower() or "jam" in error_message.lower():
                self.thank_you_screen.show_paper_jam_error(error_message)
            else:
                self.thank_you_screen.show_printing_error(error_message)
        else:
            print(f"⚠️ Print failed on wrong screen. Error: {error_message}")

    def cleanup(self):
        """
        Clean up all application resources before shutdown.
        
        Stops background threads, cleans up USB monitoring, and properly
        shuts down the SMS system. Called automatically on application close.
        """
        try:
            print("🧹 Starting application cleanup...")
            
            # Stop database operations first to prevent SQLite thread errors
            if hasattr(self, 'db_threader'):
                print("🔄 Stopping database threader...")
                self.db_threader.stop()
            if hasattr(self, 'ink_analysis_threader'):
                print("🔄 Stopping ink analysis threader...")
                self.ink_analysis_threader.stop()
            
            # Stop USB monitoring thread
            if hasattr(self, 'usb_screen') and hasattr(self.usb_screen, 'model'):
                print("🔄 Stopping USB monitoring...")
                self.usb_screen.model.stop_usb_monitoring()
            
            # Clean up database connections before other cleanup
            try:
                from utils.error_logger import cleanup_db_connections
                print("🔄 Cleaning up database connections...")
                cleanup_db_connections()
            except Exception as db_cleanup_error:
                print(f"⚠️ Error cleaning up database connections: {db_cleanup_error}")
            
            # Clean up SMS system
            print("🔄 Cleaning up SMS system...")
            cleanup_sms()
            
            # Clean up persistent GPIO last
            print("🔄 Cleaning up persistent GPIO...")
            cleanup_persistent_gpio()
            
            print("✅ Application cleanup completed")
                
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

    def closeEvent(self, event):
        """
        Qt event handler for window close.
        
        Args:
            event: QCloseEvent from Qt framework
        """
        self.cleanup()
        event.accept()


def main():
    """
    Application entry point.
    
    Initializes the database, creates the Qt application, and starts the main event loop.
    Shows the window in fullscreen mode for kiosk deployment.
    """
    try:
        print("\n🔄 Initializing database...")
        init_db()
        print("✅ Database initialization successful\n")
        
        # Create Qt application
        app = QApplication(sys.argv) # Main thread init
        app.setApplicationName("Printing System GUI")
        app.setApplicationVersion("1.0")
        window = PrintingSystemApp()

        # Show window (size and mode determined by _setup_display)
        window.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"❌ Error during initialization: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
