# screens/voucher_balance/controller.py
#
# "Check voucher balance", reached from the homepage without starting a print
# job. Returns to the homepage on Back, or to idle after the usual 60s of inactivity.

from PyQt5.QtWidgets import QWidget, QGridLayout

from managers.timeout_manager import TimeoutPolicy
from managers.voucher_manager import CODE_ALPHABET
from .model import VoucherBalanceModel
from .view import VoucherBalanceScreenView

TIMEOUT_MS = 60000


class VoucherBalanceController(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = VoucherBalanceModel()
        self.view = VoucherBalanceScreenView(code_keys=CODE_ALPHABET)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)

        self.view.check_clicked.connect(self.check_voucher_code)
        self.view.back_button_clicked.connect(self._go_back)

    def check_voucher_code(self, raw_code):
        """Check a typed code or a 'V1:<code>' payload, so a QR read can be
        passed straight in."""
        self.model.check(raw_code)
        self.view.render(self.model)

    def _go_back(self):
        self.main_app.show_screen('homepage')

    # --- Lifecycle (called by main_app.show_screen) ---

    def on_enter(self):
        print("Voucher balance screen entered")
        self.model.clear()
        self.view.clear()

    def on_leave(self):
        print("Voucher balance screen leaving")
        self.model.clear()
        self.view.clear()

    def timeout_policy(self):
        return TimeoutPolicy(seconds=TIMEOUT_MS // 1000, action=self._on_timeout)

    def _on_timeout(self):
        print("Voucher balance screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
