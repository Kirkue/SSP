# screens/scanner/controller.py

import time

from PyQt5.QtWidgets import QWidget, QGridLayout
from PyQt5.QtCore import QTimer

from managers.scan_progress import progress_fraction

from .model import ScannerModel
from .view import ScannerScreenView


class ScannerController(QWidget):
    """Manages the Scanner screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScannerModel()
        self.view = ScannerScreenView()
        self._scan_completed = False

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

        # Paces the progress bar while a page is being scanned
        self._progress_started = None
        self._progress_expected = 0.0
        self.progress_timer = QTimer()
        self.progress_timer.setInterval(200)
        self.progress_timer.timeout.connect(self._tick_progress)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        self.view.cancel_clicked.connect(self._handle_cancel)
        self.view.cancel_clicked.connect(self._reset_timeout)

        self.view.scan_page_clicked.connect(self._handle_scan_page)
        self.view.scan_page_clicked.connect(self._reset_timeout)

        self.view.rescan_clicked.connect(self._handle_rescan)
        self.view.rescan_clicked.connect(self._reset_timeout)

        self.view.done_clicked.connect(self._handle_done)
        self.view.done_clicked.connect(self._reset_timeout)

        self.view.colour_toggled.connect(self.model.set_colour)
        self.view.colour_toggled.connect(self._reset_timeout)

        self.model.busy_changed.connect(self._on_busy_changed)
        self.model.page_scanned.connect(self._handle_page_scanned)
        self.model.scan_failed.connect(self._handle_scan_failed)
        self.model.scan_finished.connect(self._handle_scan_finished)
        self.model.finish_failed.connect(self._handle_finish_failed)

    def _handle_scan_page(self):
        self._start_progress("Scanning")
        self.model.scan_page()

    def _handle_rescan(self):
        self._start_progress("Rescanning last page")
        self.model.rescan_last()

    def _start_progress(self, what):
        self._progress_expected = self.model.expected_scan_seconds()
        self._progress_started = time.monotonic()
        self.view.show_status(f"{what}... about {round(self._progress_expected)} seconds.", is_error=False)
        self.view.show_progress(0.0)
        self.progress_timer.start()

    def _tick_progress(self):
        if self._progress_started is None:
            return
        elapsed = time.monotonic() - self._progress_started
        self.view.show_progress(progress_fraction(elapsed, self._progress_expected))

    def _stop_progress(self):
        self.progress_timer.stop()
        self._progress_started = None
        self.view.hide_progress()

    def _on_busy_changed(self, busy):
        self.view.set_busy(busy)
        if not busy:
            self._stop_progress()

    def _handle_page_scanned(self, page_number, image_path):
        self.view.update_page_count(page_number)
        self.view.show_preview(image_path, page_number)
        self.view.show_status(f"Page {page_number} scanned.", is_error=False)

    def _handle_scan_failed(self, message):
        self.view.show_status(message, is_error=True)

    def _handle_done(self):
        self.view.show_status("Preparing your document...", is_error=False)
        self.model.finish()

    def _handle_scan_finished(self, pdf_path, page_count):
        self._scan_completed = True
        self.main_app.scan_destination_screen.set_scan_result(pdf_path, page_count)
        self.main_app.show_screen('scan_destination')

    def _handle_finish_failed(self, message):
        self.view.show_status(message, is_error=True)

    def _handle_cancel(self):
        self.model.cancel()
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("Scanner screen entered")
        self._scan_completed = False
        self.model.start_session()
        self._stop_progress()
        self.view.reset(self.model.colour)
        self.timeout_timer.start(60000)

    def on_leave(self):
        print("Scanner screen leaving")
        self.timeout_timer.stop()
        self._stop_progress()
        if not self._scan_completed:
            self.model.cancel()

    def _on_timeout(self):
        print("⏰ Scanner screen timeout - returning to homepage")
        self.model.cancel()
        self.main_app.show_screen('homepage')

    def _reset_timeout(self):
        if self.main_app.stacked_widget.currentWidget() is not self:
            return
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        if hasattr(self.main_app, "start_global_countdown"):
            self.main_app.start_global_countdown(60)
