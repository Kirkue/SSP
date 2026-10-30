# screens/scanner/model.py
#
# Real multi-page capture backed by ScannerManager (managers/scanner_manager.py)
# — replaces the earlier stub that faked success and dev-bypassed into
# test_pdfs/. scan_page/rescan_last/finish run off the main thread via
# ScannerThread since real hardware can block for tens of seconds;
# start_session/cancel are cheap file-IO and run directly.

from PyQt5.QtCore import QObject, pyqtSignal

from config import get_config
from managers.scanner_manager import ScannerManager
from managers.scanner_thread import ScannerThread


class ScannerModel(QObject):
    """Handles data and logic for the Scanner screen."""
    page_scanned = pyqtSignal(int, str)     # (page_number, image_path)
    scan_failed = pyqtSignal(str)
    scan_finished = pyqtSignal(str, int)    # (pdf_path, page_count)
    finish_failed = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.manager = ScannerManager()
        self.thread = None

    def start_session(self):
        self.manager.start_session()
        self.manager.colour = get_config().scanner_colour_default

    @property
    def colour(self) -> bool:
        return self.manager.colour

    def set_colour(self, colour: bool):
        self.manager.colour = bool(colour)

    def expected_scan_seconds(self) -> float:
        return self.manager.expected_scan_seconds()

    def page_count(self) -> int:
        return self.manager.page_count()

    def scan_page(self):
        self._start_operation(self.manager.scan_page, self._on_scan_done, self.scan_failed)

    def rescan_last(self):
        self._start_operation(self.manager.rescan_last, self._on_scan_done, self.scan_failed)

    def finish(self):
        self._start_operation(self.manager.finish, self._on_finish_done, self.finish_failed)

    def cancel(self):
        self.manager.cancel()

    def _start_operation(self, operation, success_handler, failure_signal):
        if self.thread is not None and self.thread.isRunning():
            failure_signal.emit("A scan operation is already in progress.")
            return

        self.busy_changed.emit(True)
        self.thread = ScannerThread(operation)
        self.thread.operation_succeeded.connect(success_handler)
        self.thread.operation_failed.connect(failure_signal.emit)
        self.thread.operation_succeeded.connect(self._on_operation_finished)
        self.thread.operation_failed.connect(self._on_operation_finished)
        self.thread.finished.connect(self._on_thread_finished)
        self.thread.start()

    def _on_operation_finished(self, *_args):
        self.busy_changed.emit(False)

    def _on_thread_finished(self):
        self.thread = None

    def _on_scan_done(self, result):
        self.page_scanned.emit(result["page_number"], result["path"])

    def _on_finish_done(self, result):
        self.scan_finished.emit(result["pdf_path"], result["page_count"])
