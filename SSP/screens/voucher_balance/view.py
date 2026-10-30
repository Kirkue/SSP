# screens/voucher_balance/view.py
#
# The "Check voucher balance" popup: a full-window dimmed overlay (so nothing underneath can
# be tapped) with a card holding the code entry, keypad and result: a Voucher's remaining
# value and expiry, nothing else. Contains no logic; the controller feeds it from
# VoucherBalanceModel.

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT, RADIUS
from ui.widgets import BackButton, CodeKeypad, PrimaryButton, ReaderHint, StatusBanner

SUBTITLE = "Enter your voucher code to see how much is left on it."


class VoucherBalancePopupView(QFrame):
    check_clicked = pyqtSignal(str)  # code_text
    close_clicked = pyqtSignal()

    def __init__(self, code_keys, parent=None):
        super().__init__(parent)
        self._code_keys = code_keys  # characters the on-screen keypad offers
        self.setup_ui()
        self.hide()

    def setup_ui(self):
        self.setObjectName("VoucherBalancePopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#VoucherBalancePopup { background-color: rgba(0, 0, 0, 140); }")

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("VoucherBalanceCard")
        self.card.setFixedWidth(760)
        self.card.setStyleSheet(
            f"QFrame#VoucherBalanceCard {{ background-color: {COLORS['bg']}; border-radius: {RADIUS['lg']}px; }}"
        )
        outer.addWidget(self.card)

        body = QVBoxLayout(self.card)
        body.setContentsMargins(36, 28, 36, 24)
        body.setSpacing(10)

        title = QLabel("Check voucher balance")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        self.subtitle = QLabel(SUBTITLE)
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        # "Hold your QR code up to the reader, or type your code." Hidden when the kiosk has
        # no reader (QR_READER_PORT blank), so it never asks for a scan nothing would read.
        self.reader_hint = ReaderHint()

        entry_row = QHBoxLayout()
        entry_row.setSpacing(6)
        entry_row.addStretch()

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("XXXX-XXXX")
        self.code_input.setMaxLength(16)  # room for 'V1:' and spaces; normalize_code decides
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMinimumWidth(260)
        self.code_input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 8px; "
            f"font-size: {FONT['size_lg']}px; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )
        self.code_input.returnPressed.connect(self._emit_check)

        self.check_button = PrimaryButton("Check balance")
        self.check_button.clicked.connect(self._emit_check)

        entry_row.addWidget(self.code_input)
        entry_row.addWidget(self.check_button)
        entry_row.addStretch()

        # The touchscreen has no keyboard, so the code is typed on this keypad.
        self.keypad = CodeKeypad(self.code_input, self._code_keys)

        # Remaining value and expiry; hidden until a code is found.
        self.result_panel = QWidget()
        result = QVBoxLayout(self.result_panel)
        result.setContentsMargins(0, 0, 0, 0)
        result.setSpacing(4)

        caption = QLabel("Remaining value")
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.amount_label = QLabel("")
        self.amount_label.setAlignment(Qt.AlignCenter)
        self.amount_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: {FONT['size_display']}px; font-weight: 800;"
        )

        self.expiry_label = QLabel("")
        self.expiry_label.setAlignment(Qt.AlignCenter)
        self.expiry_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 600;"
        )

        self.saved_note = QLabel("")
        self.saved_note.setAlignment(Qt.AlignCenter)
        self.saved_note.setWordWrap(True)
        self.saved_note.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px; font-weight: 600;"
        )

        result.addWidget(caption)
        result.addWidget(self.amount_label)
        result.addWidget(self.expiry_label)
        result.addWidget(self.saved_note)
        self.result_panel.hide()

        self.status_banner = StatusBanner()

        self.close_button = BackButton("Close")
        self.close_button.setMinimumHeight(52)
        self.close_button.clicked.connect(self.close_clicked.emit)

        body.addWidget(title)
        body.addWidget(self.subtitle)
        body.addWidget(self.reader_hint)
        body.addSpacing(4)
        body.addLayout(entry_row)
        body.addWidget(self.keypad, 0, Qt.AlignHCenter)
        body.addWidget(self.result_panel)
        body.addWidget(self.status_banner)
        body.addSpacing(4)
        body.addWidget(self.close_button)

    def _emit_check(self):
        self.check_clicked.emit(self.code_input.text())

    def show_popup(self):
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self.code_input.setFocus()

    def hide_popup(self):
        self.hide()

    def render(self, model, remembered_note: str = ""):
        """Paint the current VoucherBalanceModel. Called by the controller."""
        self.result_panel.setVisible(model.found)
        self.amount_label.setText(model.amount_text())
        self.expiry_label.setText(model.expiry_text())
        self.saved_note.setText(remembered_note if model.found else "")
        if model.found:
            # The code has done its job; don't leave it on screen.
            self.code_input.clear()
            self.status_banner.show_message("")
        else:
            self.status_banner.show_message(model.message, "error")

    def clear(self):
        self.code_input.clear()
        self.amount_label.setText("")
        self.expiry_label.setText("")
        self.saved_note.setText("")
        self.result_panel.hide()
        self.status_banner.show_message("")
