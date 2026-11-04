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
import signal
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QInputDialog, QShortcut, QGraphicsDropShadowEffect
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence
from screens.idle import IdleController
from screens.payment.model import redirect_for_carried_credit
from screens.usb import USBController
from screens.wifi import WifiController
from screens.email import EmailController
from screens.homepage import HomepageController
from screens.scanner import ScannerController
from screens.scan_destination import ScanDestinationController
from screens.scan_result import ScanResultController
from screens.file_browser import FileBrowserController
from screens.payment import PaymentController
from screens.print_options import PrintOptionsController
from screens.admin import AdminController
from screens.data_viewer import DataViewerController
from screens.voucher import VoucherController
from screens.voucher_balance import VoucherBalanceController
from screens.thank_you import ThankYouController
from database.models import init_db
from managers.printer_manager import PrinterManager
from managers.hopper_manager import stop_all_hopper_motors
from managers.db_threader import DatabaseThreadManager
from managers.ink_analysis_threader import InkAnalysisThreadManager
from managers.ink_supply import empty_cartridges, format_alerted, low_ink_alerts, low_ink_message, parse_alerted
from managers.webapp_thread import WebAppThreadManager
from managers.email_poller_thread import EmailPollerThreadManager
from managers.qr_reader import (CONNECTED, DuplicateReadFilter, QrReaderManager, classify_payload, decide_qr_read,
                                describe_reader_status, should_log_status_change)
from managers.kiosk_status import SETTING_LAST_SEEN, SETTING_QR_STATUS, heartbeat_timestamp
from managers.session_manager import SessionManager
from managers.session_vouchers import SessionVouchers
from database.db_manager import DatabaseManager
from managers.sms_manager import cleanup_sms
from managers.print_refund import record_print_success, refund_failed_print
from screens.voucher.model import VoucherModel
from managers.persistent_gpio import cleanup_persistent_gpio
from managers.gpio_check import gpio_problem
from config import get_config
from ui.scaling import apply_ui_scale, pin_render_environment
from managers.timeout_manager import TimeoutManager
from ui.activity_filter import ActivityFilter
from ui.tap_guard import ScreenChangeTapGuard
from ui.timeout_warning import TimeoutWarning
from ui.theme import apply_theme, render_summary, COLORS


class _QrReadBridge(QObject):
    """Carries reads from the QR reader's thread to the GUI thread (a signal
    emitted off-thread is delivered queued on the receiver's thread)."""
    read = pyqtSignal(str)


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
        'homepage': 1,
        'usb': 2,
        'wifi': 3,
        'email': 4,
        'scanner': 5,
        'file_browser': 6,
        'printing_options': 7,
        'payment': 8,
        'admin': 9,
        'data_viewer': 10,
        'thank_you': 11,
        'scan_destination': 12,
        'scan_result': 13,
        'voucher': 14,
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

        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import Qt

        self.global_timer_label = QLabel("Remaining Time: 60s", self)
        self.global_timer_label.setAlignment(Qt.AlignCenter)
        # White chip with charcoal text and a soft shadow, sized to its text (see _place_timer_label).
        self.global_timer_label.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
                font-size: 18px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self.global_timer_label)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.global_timer_label.setGraphicsEffect(shadow)
        self._place_timer_label()
        self.global_timer_label.hide()

        # The one inactivity timeout (managers/timeout_manager.py): it drives the label above
        # and the "Still there?" prompt, and runs each screen's timeout action.
        config = get_config()
        self.timeouts = TimeoutManager(config.timeout_warning_seconds, config.timeout_extend_seconds, parent=self)
        self.timeout_warning = TimeoutWarning(config.timeout_extend_seconds, self)
        self.timeouts.tick.connect(self._on_timeout_tick)
        self.timeouts.warning_shown.connect(self.timeout_warning.show_warning)
        self.timeouts.tick.connect(self.timeout_warning.update_remaining)
        self.timeouts.warning_hidden.connect(self.timeout_warning.hide_warning)
        self.timeouts.expired.connect(self._on_screen_timeout)
        self.timeout_warning.extend_clicked.connect(self.timeouts.extend)
        # Any tap counts as activity. Installed before the tap guard so the guard, which
        # Qt runs first, can drop a doubled tap before it gets here.
        self.activity_filter = ActivityFilter(self.timeouts.note_tap, parent=self)
        QApplication.instance().installEventFilter(self.activity_filter)

        # Drops the panel's doubled tap that would land on the next screen (ui/tap_guard.py)
        self.tap_guard = ScreenChangeTapGuard(parent=self)
        QApplication.instance().installEventFilter(self.tap_guard)

        # Initialize all screen controllers
        self.idle_screen = IdleController(self)
        self.homepage_screen = HomepageController(self)
        self.usb_screen = USBController(self)
        self.wifi_screen = WifiController(self)
        self.email_screen = EmailController(self)
        self.scanner_screen = ScannerController(self)
        self.file_browser_screen = FileBrowserController(self)
        self.printing_options_screen = PrintOptionsController(self)
        self.payment_screen = PaymentController(self)
        self.admin_screen = AdminController(self)

        # Initialize thread managers for background operations
        self.db_threader = DatabaseThreadManager()
        self.ink_analysis_threader = InkAnalysisThreadManager()
        self.db_threader.start()
        self.ink_analysis_threader.start()
        self.webapp_thread = WebAppThreadManager.from_config()
        self.webapp_thread.start()
        try:
            self.email_poller_thread = EmailPollerThreadManager.from_config()
            self.email_poller_thread.start()
        except Exception as e:
            print(f"⚠️ Failed to start email poller thread: {e}")
            self.email_poller_thread = None

        # Connect thread managers for real-time data updates
        self._connect_thread_managers()

        self._setup_qr_reader()
        self._setup_kiosk_status()

        # Initialize printer manager (no dependencies)
        self.printer_manager = PrinterManager()

        # Set when the printer reported the tray empty, until its print_failed arrives
        # (the printer thread already sent the out-of-paper SMS for it)
        self._paper_empty_reported = False

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
        self.scan_destination_screen = ScanDestinationController(self)
        self.scan_result_screen = ScanResultController(self)
        self.voucher_screen = VoucherController(self)

        # Connect payment completion to the print workflow once screens exist.
        self.payment_screen.payment_completed.connect(self.on_payment_completed)

        # Add all screens to stacked widget in order (see SCREEN_MAP)
        self.stacked_widget.addWidget(self.idle_screen)
        self.stacked_widget.addWidget(self.homepage_screen)
        self.stacked_widget.addWidget(self.usb_screen)
        self.stacked_widget.addWidget(self.wifi_screen)
        self.stacked_widget.addWidget(self.email_screen)
        self.stacked_widget.addWidget(self.scanner_screen)
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
        self.stacked_widget.addWidget(self.scan_destination_screen)
        self.stacked_widget.addWidget(self.scan_result_screen)
        self.stacked_widget.addWidget(self.voucher_screen)

        # "Check voucher balance" is a popup over whichever screen opened it, not a screen
        # (screens/voucher_balance); the Vouchers it checks are remembered for the session.
        self.session_vouchers = SessionVouchers()
        self.voucher_balance = VoucherBalanceController(self, parent_widget=self)

        # Manually disable payment acceptors at startup
        print("🔄 Disabling payment acceptors at startup...")
        pi = None
        try:
            import pigpio  # type: ignore[import-not-found]
            pi = pigpio.pi()
            if pi.connected:
                # Disable bill acceptor (pin 23) - HIGH = disabled
                pi.write(23, 1)
                print("✅ Bill acceptor disabled (pin 23)")
                # Disable coin acceptor (pin 22) - LOW = disabled
                pi.write(22, 0)
                print("✅ Coin acceptor disabled (pin 22)")
                print("✅ Payment acceptors manually disabled at startup")
            else:
                print("⚠️ pigpio not connected - acceptors remain in default state")
        except ImportError:
            print("⚠️ pigpio is not installed; payment acceptors remain in default state")
        except Exception as e:
            print(f"⚠️ Could not disable acceptors manually: {e}")
        finally:
            # Ensure proper cleanup of GPIO connection
            if pi is not None:
                try:
                    pi.stop()
                    print("🔄 GPIO connection cleaned up")
                except Exception as cleanup_error:
                    print(f"⚠️ GPIO cleanup warning: {cleanup_error}")

        # A run that crashed or was killed mid-payout can leave a hopper motor running
        stop_all_hopper_motors()

        # Show idle screen as initial screen
        self.show_screen('idle')

        # Connect printer manager signals immediately after initialization
        print("DEBUG: Connecting printer manager signals after initialization")
        self.printer_manager.print_job_successful.connect(self.on_print_successful)
        self.printer_manager.print_job_failed.connect(self.on_print_failed)
        self.printer_manager.print_job_waiting.connect(self.on_print_waiting)
        self.printer_manager.paper_empty.connect(self.on_printer_paper_empty)
        print("DEBUG: Printer manager signals connected successfully with QueuedConnection")

        # Signal connection established successfully
        print("DEBUG: Signal connection established successfully")

        # Apply application-wide styles
        self.setStyleSheet("""
            QMainWindow {
                background-color: transparent;
            }
        """)

    def _setup_qr_reader(self):
        """Start the QR reader thread (if QR_READER_PORT is set) and, in SIM
        mode only, the dev shortcut that injects a read from a text box."""
        # Built on the GUI thread: SessionManager's DB connection is used here only.
        self.qr_session_manager = SessionManager(DatabaseManager())
        self._qr_duplicates = DuplicateReadFilter()
        self._qr_bridge = _QrReadBridge()
        self._qr_bridge.read.connect(self._on_qr_read)
        self.qr_reader = QrReaderManager.from_config(self._qr_bridge.read.emit, self._on_qr_reader_status,
                                                     self._on_qr_reader_config_error)
        if self.qr_reader is not None:
            self.qr_reader.start()
            print("✅ QR reader started")
        else:
            print("ℹ️ QR reader off — typed codes only")
            if get_config().qr_reader_port:
                # Port is configured but the reader can't run (pyserial missing): a fault, not "off".
                from utils.error_logger import log_error
                log_error("QR Reader", "QR_READER_PORT is set but pyserial is not installed", "qr_reader")

        if get_config().sim_mode:
            self._qr_inject_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Q"), self)
            self._qr_inject_shortcut.activated.connect(self._inject_qr_read)

    def _setup_kiosk_status(self):
        """Write the kiosk heartbeat and QR reader status to the DB for the Admin
        Dashboard, then refresh the heartbeat about once a minute. Writes go
        through db_threader so they're serialized with every other DB write and
        a failure never disturbs the kiosk (issue #42)."""
        self._write_heartbeat()
        self._write_qr_reader_status()
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._write_heartbeat)
        self._heartbeat_timer.start(60_000)

    def _write_heartbeat(self):
        self.db_threader.update_setting(SETTING_LAST_SEEN, heartbeat_timestamp())

    def _write_qr_reader_status(self):
        """Persist the same one-line status Kiosk Admin shows."""
        self.db_threader.update_setting(SETTING_QR_STATUS, self.qr_reader_status_text())

    def _on_qr_reader_status(self, status, previous, detail):
        """Runs on the reader thread. Loss and recovery each get one error_log entry;
        every change refreshes qr_reader_status for the dashboard."""
        if should_log_status_change(status, previous):
            from utils.error_logger import log_error
            message = ("QR reader recovered" if status == CONNECTED
                       else f"QR reader unavailable, typed codes only ({detail})")
            log_error("QR Reader", message, "qr_reader")
        # db_threader is thread-safe (queue-backed), so this reader-thread call is fine.
        self.db_threader.update_setting(SETTING_QR_STATUS, describe_reader_status(self.qr_reader))

    def _on_qr_reader_config_error(self, detail):
        """Runs on the reader thread, once per port open where a code was NAKed or unanswered."""
        from utils.error_logger import log_error
        log_error("QR Reader", f"Reader config not fully applied ({detail})", "qr_reader")

    def qr_reader_status_text(self):
        reader = getattr(self, 'qr_reader', None)
        if reader is None and get_config().qr_reader_port:
            return "Not connected (pyserial missing)"
        return describe_reader_status(reader)

    def _inject_qr_read(self):
        text, ok = QInputDialog.getText(self, "SIM: inject QR read", "QR payload:")
        if ok:
            self._on_qr_read(text.strip())

    def _current_screen_name(self):
        index = self.stacked_widget.currentIndex()
        return next((name for name, i in self.SCREEN_MAP.items() if i == index), None)

    def _qr_context(self):
        """Where a QR read lands: the balance popup while it's open (a Voucher read then
        checks the balance, whatever screen is underneath), otherwise the screen showing."""
        if self.voucher_balance.is_open:
            return 'voucher_balance'
        return self._current_screen_name()

    def open_voucher_balance(self):
        """The "Check voucher balance" popup, over the current screen."""
        self.voucher_balance.open()

    def _on_qr_read(self, text):
        """One read from the reader (or the SIM injector): de-duplicate, classify, decide, act."""
        self.note_activity()   # someone is at the kiosk, even if the read is rejected
        if self._qr_duplicates.is_duplicate(text):
            print("QR read ignored: identical read just now")
            return
        read = classify_payload(text)
        screen = self._qr_context()
        outcome = decide_qr_read(read, screen, self.qr_session_manager)
        print(f"QR read ({read.kind}) on '{screen}' -> {outcome.action}: {outcome.message}")
        if outcome.action == "open_files":
            if not self.open_session_files(outcome.source, outcome.files):
                print("⚠️ QR read verified but the session's files could not be loaded")
        elif outcome.action == "rejected":
            # Only accepting screens get here, and each has a show_qr_message().
            self.stacked_widget.currentWidget().show_qr_message(outcome.message)
        elif outcome.action == "apply_voucher":
            self.payment_screen.apply_voucher_code(text)
        elif outcome.action == "check_voucher":
            self.voucher_balance.check_voucher_code(text)

    def open_session_files(self, source, files):
        """Load a redeemed wifi/email Session's files into file_browser — the one
        path both a correct typed OTP and a read QR payload take. Returns False
        if none of the files could be loaded."""
        from managers.usb_file_manager import USBFileManager  # same import the wifi/email controllers used
        source_paths = [f['path'] for f in files]
        names = [f.get('original_filename') for f in files]
        pdf_files = USBFileManager().scan_and_copy_pdf_files_by_paths(source_paths, names)
        if not pdf_files:
            return False
        self.file_browser_screen.set_source(source)
        self.file_browser_screen.load_pdf_files(pdf_files)
        self.show_screen('file_browser')
        return True

    def _setup_display(self):
        """
        Configure display settings using the real screen resolution, then go fullscreen.
        """
        # availableGeometry() (not geometry()) excludes space reserved by OS
        # chrome (macOS menu bar + Dock on a dev laptop). Sizing to the full
        # screen geometry there caused the window manager to shift the window
        # down to clear the menu bar without shrinking it, pushing the bottom
        # controls bar off the visible screen. The real kiosk display has no
        # such chrome, so availableGeometry() == geometry() there.
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen_geometry)
        self.setMinimumSize(screen_geometry.size())

        # Set window flags for kiosk-like behavior
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint)

        # Go fullscreen on startup
        print(f"🖥️ Starting in fullscreen mode ({screen_geometry.width()}x{screen_geometry.height()})")
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
        self.ink_analysis_threader.analysis_completed.connect(self._handle_analysis_result)

    def _handle_analysis_result(self, result):
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
            self._alert_low_ink(result['cmyk_levels'])

    def _alert_low_ink(self, levels):
        """SMS the operator once per tank that has fallen to the low-ink threshold. The
        alerted tanks are kept in the settings table, so a tank is only re-alerted after
        it has been topped back above the threshold."""
        try:
            db = self.admin_screen.db_manager
            already = parse_alerted(db.get_setting('ink_low_alerted', default=''))
            to_alert, alerted = low_ink_alerts(levels, already, get_config().ink_low_alert_percent)
            if alerted != already:
                db.update_setting('ink_low_alerted', format_alerted(alerted))
            if to_alert:
                print(f"⚠️ Low ink alert: {to_alert}")
                from managers.sms_manager import send_operator_alert
                send_operator_alert(low_ink_message(to_alert))
        except Exception as e:
            print(f"⚠️ Low ink alert failed: {e}")

    def check_paper_count_and_redirect(self, allow_admin_access=False):
        """
        Check current paper count and redirect to error screen if needed.

        Args:
            allow_admin_access: If True, allows navigation to admin screen even with low paper

        Returns:
            bool: True if redirected to error screen, False if paper is available
        """
        paper_count = self.admin_screen.get_paper_count()
        if paper_count <= 3:
            print(f"⚠️ Low paper detected: {paper_count} pages remaining. Redirecting to error screen.")
            self.show_screen('thank_you')
            # Show the no paper error on the thank you screen
            self.thank_you_screen.show_no_paper_error(paper_count)
            return True
        return False

    def _empty_ink_cartridges(self):
        """{cartridge: level%} for each tank an admin has marked empty (0%); {} if none or unknown.
        Low ink alone never stops the kiosk: the levels are estimates and customers can't
        see the tanks, so only the operator's own 'empty' does (managers/ink_supply.py)."""
        cmyk_levels = self.admin_screen.db_manager.get_cmyk_ink_levels()
        if not cmyk_levels:
            print("No CMYK ink data available, skipping ink level check")
            return {}
        return empty_cartridges(cmyk_levels)

    def print_supplies_low(self):
        """True when printing isn't possible: paper at 3 sheets or fewer, or a tank marked empty."""
        try:
            return self.admin_screen.get_paper_count() <= 3 or bool(self._empty_ink_cartridges())
        except Exception as e:
            print(f"Error checking print supplies: {e}")
            return False

    def check_ink_levels_and_redirect(self):
        """
        Check the CMYK tanks and redirect to the error screen if an admin has marked one empty.

        Returns:
            bool: True if redirected (kiosk should stop), False if ink is acceptable.
        """
        try:
            empty_tanks = self._empty_ink_cartridges()

            if empty_tanks:
                details = ", ".join(name.capitalize() for name in empty_tanks)
                print(f"Ink tank marked empty ({details}). Redirecting to error screen.")
                self.show_screen('thank_you')
                self.thank_you_screen.show_printing_error(
                    "An ink tank is empty.\n"
                    "Please contact an administrator to refill the ink."
                )
                return True

            return False
        except Exception as e:
            print(f"Error checking ink levels: {e}")
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

        # The balance popup belongs to the screen it was opened on
        popup = getattr(self, 'voucher_balance', None)
        if popup is not None:
            popup.close()

        # Call on_leave lifecycle method for current screen
        current_widget = self.stacked_widget.currentWidget()
        if current_widget is not None and hasattr(current_widget, 'on_leave'):
            current_widget.on_leave()

        # Leaving an unfinished payment with cash in (anywhere but print options):
        # its Voucher is shown first, then the voucher screen continues here.
        screen_name = redirect_for_carried_credit(self, screen_name)

        # Check paper and ink before switching to most screens (except admin and thank_you)
        # scan_result: the customer has paid for the digital copy it shows.
        # scan_destination and a digital-only payment need no paper or ink; the
        # print choices are blocked there (and at printing_options) instead.
        digital_only_payment = (screen_name == 'payment'
                                and not self.payment_screen.model.is_print_job())
        if (screen_name not in ['admin', 'thank_you', 'voucher', 'scan_result', 'scan_destination']
                and not digital_only_payment):
            if self.check_paper_count_and_redirect():
                print(f"Cannot navigate to {screen_name} - insufficient paper")
                return
            if self.check_ink_levels_and_redirect():
                print(f"Cannot navigate to {screen_name} - low ink")
                return

        # Switch to the new screen
        target_index = self.SCREEN_MAP[screen_name]
        self.stacked_widget.setCurrentIndex(target_index)
        self.tap_guard.arm()

        if screen_name == 'idle':
            self.session_vouchers.clear()   # the next customer starts with none checked
        self._enter_timeout(screen_name)

        # Call on_enter lifecycle method for new screen
        new_widget = self.stacked_widget.currentWidget()
        print(f"DEBUG: show_screen - new_widget: {new_widget}")
        print(f"DEBUG: show_screen - hasattr(new_widget, 'on_enter'): {hasattr(new_widget, 'on_enter')}")
        if new_widget is not None and hasattr(new_widget, 'on_enter'):
            print("DEBUG: show_screen - calling new_widget.on_enter()")
            try:
                new_widget.on_enter()
                print("DEBUG: show_screen - new_widget.on_enter() completed")
            except Exception as e:
                print(f"ERROR: show_screen - new_widget.on_enter() failed with error: {e}")
                import traceback
                traceback.print_exc()

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

        # Paper count check is now handled in show_screen method

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
        print("DEBUG: on_print_successful called, about to trigger ink analysis")

        # The transaction was logged and the cash inventory updated at
        # settlement; the print outcome only completes the row (#59).
        job = getattr(self, 'current_print_job', None) or {}
        try:
            record_print_success(self.payment_screen.model.db_manager, job.get('payment_ref'))
        except Exception as e:
            print(f"⚠️ Could not mark transaction completed: {e}")

        # Update paper count immediately after print success (don't wait for ink analysis)
        self._update_paper_count_after_print()

        # Trigger ink analysis for the printed job (if print job info available).
        # It reads current_print_job, so this must run before the job is cleared.
        self._trigger_ink_analysis()

        # Clear the print job after successful completion to prevent re-printing
        print("DEBUG: Clearing current_print_job after successful completion")
        self.current_print_job = None

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
        print("DEBUG: _trigger_ink_analysis called")
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
        print(f"DEBUG: _on_ink_analysis_completed called with operation: {operation}")

        # Handle both dictionary and object formats
        if isinstance(operation, dict):
            # Direct dictionary result
            if operation.get('success', False) and operation.get('database_updated', False):
                print("✅ Ink levels updated in database")
        else:
            # Object format
            if hasattr(operation, 'error') and operation.error:
                print(f"⚠️ Ink analysis failed: {operation.error}")
            else:
                result = operation.result if hasattr(operation, 'result') else operation
                if result.get('success', False) and result.get('database_updated', False):
                    print("✅ Ink levels updated in database")

        print("DEBUG: Ink analysis completed, database updates already done after print success")

        # Always clean up temp PDF after analysis completes
        self.printer_manager.cleanup_last_temp_pdf()

    def _update_paper_count_after_print(self):
        """
        Update paper count in database after successful printing.

        This method is called after ink analysis completes, ensuring that
        paper count is only decremented after the print job actually succeeds.
        """
        if not hasattr(self, 'current_print_job') or not self.current_print_job:
            print("⚠️ No print job info available for paper count update")
            return

        try:
            # Calculate total pages printed
            selected_pages = self.current_print_job.get('selected_pages', [])
            copies = self.current_print_job.get('copies', 1)
            total_pages = len(selected_pages) * copies

            print(f"📄 Updating paper count: -{total_pages} pages (pages: {len(selected_pages)}, copies: {copies})")
            print(f"DEBUG: current_print_job details: {self.current_print_job}")

            # Use direct database access instead of async threader
            if hasattr(self, 'admin_screen') and self.admin_screen:
                # Get current paper count
                current_count = self.admin_screen.get_paper_count()
                if current_count is not None:
                    new_count = max(0, current_count - total_pages)

                    # Update paper count directly through admin screen
                    print(f"DEBUG: Calling decrement_paper_count with {total_pages} pages")
                    success = self.admin_screen.model.decrement_paper_count(total_pages)
                    print(f"DEBUG: decrement_paper_count returned: {success}")

                    if success:
                        print(f"✅ Paper count updated: {current_count} -> {new_count}")

                        # Verify the update by checking the database again
                        updated_count = self.admin_screen.get_paper_count()
                        print(f"DEBUG: Verified paper count in database: {updated_count}")
                    else:
                        print("❌ Failed to update paper count")
                else:
                    print("⚠️ Could not retrieve current paper count")
            else:
                print("⚠️ No admin screen available for paper count update")

        except Exception as e:
            print(f"❌ Error updating paper count: {e}")

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

    def on_printer_paper_empty(self):
        """The printer reports its tray empty: the paper count is wrong, so zero it and
        the kiosk stops taking customers until an admin records a refill."""
        self._paper_empty_reported = True
        try:
            self.admin_screen.model.mark_paper_empty()
        except Exception as e:
            print(f"❌ Could not zero the paper count: {e}")

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

        # Send SMS notification for all print failures (a paper-out already sent its own)
        paper_empty, self._paper_empty_reported = self._paper_empty_reported, False
        if not paper_empty:
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

        # The customer already paid: refund them with a Voucher (#59).
        if self._refund_failed_print(error_message):
            return

        # Display error on thank you screen
        if self.stacked_widget.currentWidget() == self.thank_you_screen:
            # Check if this is a paper jam error for specialized handling
            if "paper jam" in error_message.lower() or "jam" in error_message.lower():
                self.thank_you_screen.show_paper_jam_error(error_message)
            else:
                self.thank_you_screen.show_printing_error(error_message)
        else:
            print(f"⚠️ Print failed on wrong screen. Error: {error_message}")

    def _refund_failed_print(self, error_message):
        """Move the paid transaction to print_failed and issue a refund Voucher.
        Returns True if the voucher screen (or its failure notice) is now showing."""
        job, self.current_print_job = getattr(self, 'current_print_job', None), None
        ref = (job or {}).get('payment_ref')
        if not ref:
            return False
        try:
            outcome = refund_failed_print(self.payment_screen.model.db_manager, ref, error_message,
                                          already_refunded=job.get('digital_fee_refunded', 0))
        except Exception as e:
            print(f"CRITICAL: refund for failed print {ref} errored: {e}")
            return False
        if not outcome.applied:
            return False
        try:
            def to_idle():
                self.show_screen('idle')
            if outcome.voucher:
                self.voucher_screen.show_issued(outcome.voucher, reason=VoucherModel.REFUND, on_continue=to_idle)
            elif outcome.voucher_failed:
                self.voucher_screen.show_failure(outcome.amount, reason=VoucherModel.REFUND, on_continue=to_idle)
            else:
                return False
            self.show_screen('voucher')
            return True
        except Exception as e:
            print(f"CRITICAL: could not show the refund voucher: {e}")
            return False

    def _enter_timeout(self, screen_name):
        """Hand the timeout manager the screen's policy. A screen without a
        `timeout_policy()` (idle, thank_you, admin, data_viewer) has no timeout or label."""
        widget = self.stacked_widget.currentWidget()
        make_policy = getattr(widget, 'timeout_policy', None)
        try:
            policy = make_policy() if callable(make_policy) else None
        except Exception as e:
            print(f"⚠️ Could not read {screen_name}'s timeout policy: {e}")
            policy = None
        self.timeouts.enter(screen_name, policy)

    def note_activity(self):
        """Something other than a tap showed the customer is there (a coin, a bill, a QR read)."""
        self.timeouts.note_activity()

    def _on_timeout_tick(self, seconds_left):
        """Keeps the 'Remaining Time' label on the timeout manager's own countdown."""
        if seconds_left is None:
            self.global_timer_label.hide()
            return
        self.global_timer_label.setText(f"Remaining Time: {seconds_left:02d}s")
        self._place_timer_label()
        self.global_timer_label.show()

    def _on_screen_timeout(self, screen_name, action):
        """A screen's time ran out. Only acts if that screen is still the one showing, so a
        timeout can never pull the customer off a screen they've since moved to."""
        if self._current_screen_name() != screen_name:
            print(f"⏰ Ignoring stale timeout for '{screen_name}' (now on '{self._current_screen_name()}')")
            return
        print(f"⏰ '{screen_name}' timed out")
        if action is not None:
            action()

    def end_session(self):
        """Clear what a customer who walked away left behind: the copies of their USB, Wi-Fi
        and email files, and the Vouchers they checked, so the next customer can't find them."""
        self.session_vouchers.clear()
        try:
            from managers.usb_file_manager import USBFileManager
            USBFileManager().cleanup_all_temp_folders()
        except Exception as e:
            print(f"⚠️ Could not clear the session's files: {e}")

    def _place_timer_label(self):
        """Fit the chip to its text, right-aligned and vertically centred in the 72px header."""
        label = self.global_timer_label
        label.adjustSize()
        label.move(self.width() - label.width() - 28, (72 - label.height()) // 2)

    def cleanup(self):
        """
        Clean up all application resources before shutdown.

        Stops background threads, cleans up USB monitoring, and properly
        shuts down the SMS system. Called automatically on application close.
        """
        try:
            print("🧹 Starting application cleanup...")

            # Hoppers first: a motor running now would keep running after we exit
            self._stop_hoppers()

            if hasattr(self, '_heartbeat_timer'):
                print("🔄 Stopping heartbeat timer...")
                self._heartbeat_timer.stop()
            # Stop database operations first to prevent SQLite thread errors
            if hasattr(self, 'db_threader'):
                print("🔄 Stopping database threader...")
                self.db_threader.stop()
            if hasattr(self, 'ink_analysis_threader'):
                print("🔄 Stopping ink analysis threader...")
                self.ink_analysis_threader.stop()
            if hasattr(self, 'webapp_thread'):
                print("🔄 Stopping webapp thread...")
                self.webapp_thread.stop()
            if hasattr(self, 'email_poller_thread') and self.email_poller_thread:
                print("🔄 Stopping email poller thread...")
                self.email_poller_thread.stop()

            if getattr(self, 'qr_reader', None):
                print("🔄 Stopping QR reader...")
                self.qr_reader.stop()

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

    def _stop_hoppers(self):
        """Stop any change payout and switch both hopper motors off."""
        print("🔄 Stopping hopper motors...")
        try:
            model = self.payment_screen.model
            thread = getattr(model, 'dispense_thread', None)
            if thread and thread.isRunning():
                # Motors off and the payout's pigpio connection closed, so its
                # remaining coins fail instead of starting a motor again.
                model.change_dispenser.cleanup()
                thread.wait(5000)
        except Exception as e:
            print(f"⚠️ Error stopping change dispensing: {e}")
        stop_all_hopper_motors()

    def closeEvent(self, a0) -> None:
        """
        Qt event handler for window close.

        Args:
            a0: QCloseEvent from Qt framework
        """
        self.cleanup()
        if a0 is not None:
            a0.accept()


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

        pin_render_environment()

        # Without pigpio the payment screen would offer simulated coins and bills
        # to customers, so a real kiosk refuses to start instead.
        if not get_config().sim_mode:
            problem = gpio_problem()
            if problem:
                from utils.error_logger import log_error
                log_error("GPIO", f"Kiosk not started: {problem}", "main_app")
                print(f"❌ Coin/bill acceptors and hoppers unavailable: {problem}.")
                print("   Not starting. Fix the above, or set SIM_MODE=true for development.")
                sys.exit(1)

        scale = apply_ui_scale(get_config().ui_scale)
        print(f"🔍 UI scale {scale}")

        # Create Qt application
        app = QApplication(sys.argv)  # Main thread init
        app.setApplicationName("Printing System GUI")
        app.setApplicationVersion("1.0")
        apply_theme(app)
        window = PrintingSystemApp()

        # Show window (size and mode determined by _setup_display)
        window.show()
        print(f"🖌️ {render_summary(app)}")

        # Qt's event loop runs in C++, so Python never sees Ctrl+C (SIGINT) or
        # a systemd stop (SIGTERM) while it waits. Close the window on either,
        # which runs cleanup(), and wake Python every 200 ms so the handler
        # gets a chance to run. A second signal quits without cleanup.
        def _shut_down(signum, frame):
            if getattr(_shut_down, "called", False):
                print("\n🛑 Second signal, quitting without cleanup")
                os._exit(1)
            _shut_down.called = True
            print(f"\n🛑 {signal.Signals(signum).name} received, shutting down (again to force)...")
            window.close()

        signal.signal(signal.SIGINT, _shut_down)
        signal.signal(signal.SIGTERM, _shut_down)
        signal_wake = QTimer()
        signal_wake.timeout.connect(lambda: None)
        signal_wake.start(200)

        sys.exit(app.exec_())
    except Exception as e:
        print(f"❌ Error during initialization: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
