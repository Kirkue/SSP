# screens/voucher_balance/controller.py
#
# "Check voucher balance" as a popup (docs/remaining-work.md 2.2), opened from the homepage
# and print options without leaving the screen underneath: leaving print options is safe but
# customers don't know that, and a popup adds less friction than a screen change.
#
#   - While it's open a Voucher QR read checks the balance instead of doing what the screen
#     underneath would (main_app._on_qr_read).
#   - A Voucher that checks out is remembered for the session (SessionVouchers) so the
#     payment screen can offer it with a tap; it is never applied automatically.
#   - Any screen change closes it and wipes what it shows (main_app.show_screen), so it
#     can't be left open behind a timeout.

from PyQt5.QtCore import QObject

from managers.voucher_manager import CODE_ALPHABET, normalize_code
from .model import VoucherBalanceModel
from .view import VoucherBalancePopupView


class VoucherBalanceController(QObject):
    def __init__(self, main_app, parent_widget=None):
        super().__init__()
        self.main_app = main_app

        self.model = VoucherBalanceModel()
        self.view = VoucherBalancePopupView(code_keys=CODE_ALPHABET, parent=parent_widget)

        self.view.check_clicked.connect(self.check_voucher_code)
        self.view.close_clicked.connect(self.close)

    @property
    def is_open(self) -> bool:
        return not self.view.isHidden()

    def open(self):
        self.model.clear()
        self.view.clear()
        self.view.show_popup()

    def close(self):
        if not self.is_open:
            return
        self.view.hide_popup()
        self.model.clear()
        self.view.clear()

    def check_voucher_code(self, raw_code):
        """Check a typed code or a 'V1:<code>' payload, so a QR read can be passed straight in."""
        self.model.check(raw_code)
        note = ""
        if self.model.found:
            vouchers = getattr(self.main_app, 'session_vouchers', None)
            if vouchers is not None:
                vouchers.add(normalize_code(raw_code), self.model.remaining, self.model.expires_at)
                note = "Saved for this session: you can use it when you pay."
        self.view.render(self.model, note)
