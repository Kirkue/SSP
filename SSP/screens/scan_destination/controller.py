# screens/scan_destination/controller.py

import os
import shutil

from PyQt5.QtWidgets import QWidget, QGridLayout

from managers.timeout_manager import TimeoutPolicy
from .model import ScanDestinationModel
from .thumbnail_thread import ThumbnailRenderThread
from .view import PAGE_RENDER_HEIGHT, ScanDestinationScreenView


class ScanDestinationController(QWidget):
    """Manages the post-scan destination-choice screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScanDestinationModel()
        self.view = ScanDestinationScreenView()
        self.thumbnail_thread = None

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        self.view.cancel_clicked.connect(self._handle_cancel)

        self.view.continue_clicked.connect(self._handle_continue)

    # --- Public API for main_app ---

    def set_scan_result(self, pdf_path: str, page_count: int):
        self.model.set_scan_result(pdf_path, page_count)
        self.view.set_summary(page_count)
        self.view.set_digital_fee(self.model.get_digital_fee())
        self.view.reset_selection()
        self._start_thumbnail_render(pdf_path)

    def _start_thumbnail_render(self, pdf_path):
        self._stop_thumbnail_render()
        self.view.clear_thumbnails()
        self.thumbnail_thread = ThumbnailRenderThread(pdf_path, PAGE_RENDER_HEIGHT)
        self.thumbnail_thread.thumbnail_ready.connect(self.view.add_thumbnail)
        self.thumbnail_thread.finished.connect(self._on_thumbnail_thread_finished)
        self.thumbnail_thread.start()

    def _stop_thumbnail_render(self):
        if self.thumbnail_thread is not None:
            self.thumbnail_thread.stop()
            self.thumbnail_thread.wait()
            self.thumbnail_thread = None

    def _on_thumbnail_thread_finished(self):
        self.thumbnail_thread = None

    def _handle_continue(self):
        """Route the selection. Nothing is delivered before payment."""
        selected = self.view.get_selected_keys()
        wants_print = 'print' in selected
        wants_digital = 'send_wifi' in selected
        if not (wants_print or wants_digital):
            return

        if wants_print:
            fee = self.model.get_digital_fee() if wants_digital else 0
            self.main_app.printing_options_screen.set_pdf_data(
                self.model.get_pdf_data(), self.model.get_selected_pages(), "scanner", digital_fee=fee)
            self.main_app.show_screen('printing_options')
        else:
            self.main_app.payment_screen.set_payment_data(self.model.get_digital_only_payment_data())
            self.main_app.show_screen('payment')

    def _handle_cancel(self):
        self._cleanup_pdf()
        self.main_app.show_screen('homepage')

    def _cleanup_pdf(self):
        pdf_path = self.model.pdf_path
        if pdf_path and os.path.exists(pdf_path):
            try:
                shutil.rmtree(os.path.dirname(pdf_path), ignore_errors=True)
            except OSError:
                pass

    def on_enter(self):
        print("Scan destination screen entered")
        self.view.show_status("")
        self.view.set_busy(False)
        self.view.set_print_available(not self.main_app.print_supplies_low())
        self.view.set_digital_fee(self.model.get_digital_fee())

    def on_leave(self):
        print("Scan destination screen leaving")
        self._stop_thumbnail_render()

    def timeout_policy(self):
        return TimeoutPolicy(seconds=60, action=self._on_timeout)

    def _on_timeout(self):
        print("⏰ Scan destination screen timeout - returning to homepage")
        self._cleanup_pdf()
        self.main_app.show_screen('homepage')
