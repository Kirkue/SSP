# screens/email/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout

from config import get_config
from managers.timeout_manager import TimeoutPolicy

from .model import EmailModel
from .view import EmailScreenView


class EmailController(QWidget):
    """Manages the Email upload screen's logic and UI."""

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = EmailModel()
        self.view = EmailScreenView()

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
            print("Email screen: OTP accepted")

            if not self.main_app.open_session_files("email", files):
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
        print("Email screen entered")
        self.view.clear_otp_input()
        self.view.show_status("")
        try:
            config = get_config()
            self.view.set_email_hint(config.email_user, config.email_subject_keyword)
        except Exception as e:
            print(f"Could not resolve email intake hint: {e}")

    def on_leave(self):
        print("Email screen leaving")

    def refresh_files(self):
        """Called by file_browser when the user wants to add another
        email-sourced document — send them back to enter a fresh code."""
        self.main_app.show_screen('email')

    def timeout_policy(self):
        return TimeoutPolicy(seconds=60, action=self._on_timeout)

    def _on_timeout(self):
        # No file has been chosen yet, so nothing to clear: back to idle.
        print("⏰ Email screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
