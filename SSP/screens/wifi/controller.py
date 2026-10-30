# screens/wifi/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout

from managers.timeout_manager import TimeoutPolicy
from managers.webapp_thread import wifi_portal_url

from .model import WifiModel
from .view import WifiScreenView


class WifiController(QWidget):
    """Manages the WiFi upload screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = WifiModel()
        self.view = WifiScreenView()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self._connect_signals()

    def _connect_signals(self):
        self.view.back_button_clicked.connect(self._go_back)

        self.view.send_otp_clicked.connect(self._handle_send_otp)

        self.model.otp_result.connect(self._handle_otp_result)

    def _handle_send_otp(self, otp_text):
        self.model.validate_otp(otp_text)

    def _handle_otp_result(self, is_valid, message, files):
        if is_valid:
            self.view.show_status(message, is_error=False)
            print("WiFi screen: OTP accepted")

            if not self.main_app.open_session_files("wifi", files):
                self.view.show_status("Could not load the uploaded file(s).", is_error=True)
        else:
            self.view.show_status(message, is_error=True)

    def show_qr_message(self, message):
        """A message about a QR read (from main_app), shown like a typed-code error."""
        self.view.show_status(message, is_error=True)

    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Public API for main_app ---

    def on_enter(self):
        print("WiFi screen entered")
        self.view.clear_otp_input()
        self.view.show_status("")
        try:
            webapp_thread = getattr(self.main_app, "webapp_thread", None)
            tls = getattr(webapp_thread, "tls_enabled", None)
            self.view.set_portal_hint(wifi_portal_url(tls=tls))
        except Exception as e:
            print(f"Could not resolve Wi-Fi portal URL: {e}")

    def on_leave(self):
        print("WiFi screen leaving")

    def refresh_files(self):
        """Called by file_browser when the user wants to add another
        wifi-sourced document — send them back to enter a fresh code."""
        self.main_app.show_screen('wifi')

    def timeout_policy(self):
        return TimeoutPolicy(seconds=60, action=self._on_timeout)

    def _on_timeout(self):
        # No file has been chosen yet, so nothing to clear: back to idle.
        print("⏰ WiFi screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
