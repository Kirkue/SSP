# screens/scan_result/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout

from managers.timeout_manager import TimeoutPolicy
from managers.webapp_thread import scan_redeem_portal_url

from .model import ScanResultModel
from .view import ScanResultScreenView


class ScanResultController(QWidget):
    """Manages the post-scan Wi-Fi pickup screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = ScanResultModel()
        self.view = ScanResultScreenView()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.done_clicked.connect(self._handle_done)

    # --- Public API for main_app ---

    def set_session(self, session, then_print=False):
        """The digital copy is already paid for. then_print: Continue goes on to
        the (also paid-for) print, which thank_you starts."""
        self.model.set_session(session, then_print)
        self.view.set_otp(session.otp)
        self.view.set_continue_mode(self.model.has_pending_print())

    def _handle_done(self):
        if self.model.has_pending_print():
            self.main_app.show_screen('thank_you')
        else:
            self.main_app.show_screen('homepage')

    def on_enter(self):
        print("Scan result screen entered")
        try:
            webapp_thread = getattr(self.main_app, "webapp_thread", None)
            tls = getattr(webapp_thread, "tls_enabled", None)
            self.view.set_portal_hint(scan_redeem_portal_url(tls=tls))
        except Exception as e:
            print(f"Could not resolve scan redeem portal URL: {e}")

    def on_leave(self):
        print("Scan result screen leaving")

    def timeout_policy(self):
        # The customer has paid; this screen carries on by itself after 60 s whatever they
        # tap, so the countdown is fixed and there is nothing to warn about.
        return TimeoutPolicy(seconds=60, action=self._on_timeout, warn=False, taps_reset=False)

    def _on_timeout(self):
        print("⏰ Scan result screen timeout")
        # The print is paid for: carry on to it rather than abandoning it.
        self._handle_done()
