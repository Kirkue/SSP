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

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget
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
from managers.database_thread_manager import DatabaseThreadManager
from managers.ink_analysis_thread_manager import InkAnalysisThreadManager
from managers.sms_manager import cleanup_sms

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
        database_thread_manager: Manages database operations in background thread
        ink_analysis_thread_manager: Manages ink usage analysis in background thread
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
        self.setGeometry(100, 100, 1024, 600)
        self.setMinimumSize(1024, 600)

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
        self.database_thread_manager = DatabaseThreadManager()
        self.ink_analysis_thread_manager = InkAnalysisThreadManager()
        self.database_thread_manager.start()
        self.ink_analysis_thread_manager.start()
        
        # Connect thread managers for real-time data updates
        self._connect_thread_managers()
        
        # Initialize printer manager with ink analysis integration
        self.printer_manager = PrinterManager(self.ink_analysis_thread_manager)
        
        # Initialize remaining screens that depend on other components
        self.data_viewer_screen = DataViewerController(self, self.admin_screen.db_manager)
        self.thank_you_screen = ThankYouController(self)

        # Add all screens to stacked widget in order (see SCREEN_MAP)
        self.stacked_widget.addWidget(self.idle_screen)
        self.stacked_widget.addWidget(self.usb_screen)
        self.stacked_widget.addWidget(self.file_browser_screen)
        self.stacked_widget.addWidget(self.printing_options_screen)
        self.stacked_widget.addWidget(self.payment_screen)
        self.stacked_widget.addWidget(self.admin_screen)
        self.stacked_widget.addWidget(self.data_viewer_screen)
        self.stacked_widget.addWidget(self.thank_you_screen)

        # Show idle screen as initial screen
        self.show_screen('idle')

        # Apply application-wide styles
        self.setStyleSheet("""
            QMainWindow {
                background-color: transparent;
            }
        """)
    
    def _connect_thread_managers(self):
        """
        Connect signals between thread managers and application components.
        
        Sets up signal connections for:
        - Ink analysis completion and CMYK level updates
        - Payment completion to trigger printing
        - Print job status updates (success, failure, waiting)
        """
        # Connect ink analysis completion for database updates
        self.ink_analysis_thread_manager.analysis_completed.connect(self._on_ink_analysis_completed)
        
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
            self.database_thread_manager.cmyk_levels_updated.emit(result['cmyk_levels'])

        # Connect payment and printing signals after screens are ready
        self.payment_screen.payment_completed.connect(self.on_payment_completed)
        self.printer_manager.print_job_successful.connect(self.on_print_successful)
        self.printer_manager.print_job_failed.connect(self.on_print_failed)
        self.printer_manager.print_job_waiting.connect(self.on_print_waiting)

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
        
        self.printer_manager.print_file(
            file_path=payment_info['pdf_data']['path'],
            copies=payment_info['copies'],
            color_mode=payment_info['color_mode'],
            selected_pages=payment_info['selected_pages']
        )

    def on_print_successful(self):
        """
        Handle successful print job completion.
        
        Updates the thank you screen to show completion status. If not currently
        on the thank you screen, navigates to it first before updating status.
        """
        print("✅ Print job successfully completed")
        
        current_screen = self.stacked_widget.currentWidget()
        
        if current_screen == self.thank_you_screen:
            self.thank_you_screen.finish_printing()
        else:
            # Print job completed but we're on wrong screen - navigate first
            print(f"⚠️ Print completed on wrong screen ({type(current_screen).__name__}), navigating to thank you screen")
            self.show_screen('thank_you')
            QTimer.singleShot(100, lambda: self.thank_you_screen.finish_printing())

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
        
        Sends SMS notification for print failures and displays appropriate
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
            # Stop USB monitoring thread
            if hasattr(self, 'usb_screen') and hasattr(self.usb_screen, 'model'):
                self.usb_screen.model.stop_usb_monitoring()
            
            # Clean up SMS system
            cleanup_sms()
            
            # Stop thread managers
            if hasattr(self, 'database_thread_manager'):
                self.database_thread_manager.stop()
            if hasattr(self, 'ink_analysis_thread_manager'):
                self.ink_analysis_thread_manager.stop()
                
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
        app = QApplication(sys.argv)
        app.setApplicationName("Printing System GUI")
        app.setApplicationVersion("1.0")
        window = PrintingSystemApp()

        # Show fullscreen for kiosk mode (use window.show() for development)
        window.showFullScreen()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"❌ Error during initialization: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
