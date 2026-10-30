# screens/payment/view.py

from html import escape

from PyQt5.QtWidgets import QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt5.QtCore import Qt, pyqtSignal

from config import get_config
from ui.theme import COLORS, FONT
from ui.widgets import Header, BackButton, CodeKeypad, PrimaryButton, SecondaryButton, StatusBanner, NAV_EDGE_INSET, nav_button


def _classify_status_variant(status_text: str) -> str:
    text = status_text.lower()
    if "error" in text or "fail" in text or "insufficient" in text:
        return "error"
    if any(kw in text for kw in ("success", "dispensed", "sufficient", "received", "complete")):
        return "success"
    return "info"


class PaymentScreenView(QWidget):
    """View for the Payment screen - handles UI components and presentation."""

    # Signals for user interactions
    back_button_clicked = pyqtSignal()
    simulation_coin_clicked = pyqtSignal(int)  # coin_value
    simulation_bill_clicked = pyqtSignal(int)  # bill_value
    voucher_code_entered = pyqtSignal(str)     # raw text from the "Use a voucher" entry
    voucher_entry_activity = pyqtSignal()      # typing in the entry (keeps the screen awake)
    checked_voucher_clicked = pyqtSignal(str)  # canonical code of a voucher checked earlier this session

    def __init__(self, voucher_keys, parent=None):
        super().__init__(parent)
        self._voucher_keys = voucher_keys  # characters the on-screen keypad offers
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the screen."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(Header())

        body = QWidget()
        body.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(30, 20, 30, 30)
        body_layout.setSpacing(10)
        main_layout.addWidget(body, 1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(NAV_EDGE_INSET, NAV_EDGE_INSET, NAV_EDGE_INSET, 0)
        self.back_btn = nav_button(BackButton("Back to Options"))
        self.back_btn.clicked.connect(self.back_button_clicked.emit)
        top_row.addWidget(self.back_btn)
        top_row.addStretch()
        body_layout.addLayout(top_row)

        body_layout.addStretch(1)

        # Receipt card: the job's line items, then the total underneath a divider.
        receipt = QFrame()
        receipt.setObjectName("Receipt")
        receipt.setStyleSheet(
            f"QFrame#Receipt {{ background-color: {COLORS['bg_subtle']}; "
            f"border: 1px solid {COLORS['border_strong']}; border-radius: 10px; }}"
            f"QFrame#Receipt QLabel {{ background: transparent; border: none; }}"
        )
        receipt_layout = QVBoxLayout(receipt)
        receipt_layout.setContentsMargins(24, 16, 24, 16)
        receipt_layout.setSpacing(8)

        # Summary label (rich-text line items, filled by update_payment_data)
        self.summary_label = QLabel("Print Job Summary")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.RichText)
        self.summary_label.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_md']}px;")
        receipt_layout.addWidget(self.summary_label)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {COLORS['border_strong']}; border: none;")
        receipt_layout.addWidget(divider)

        # Total label
        self.total_label = QLabel()
        self.total_label.setTextFormat(Qt.RichText)
        self._set_total(0)
        receipt_layout.addWidget(self.total_label)

        # Capped width, centred: label and value stay close enough to read as one row.
        receipt.setFixedWidth(640)
        receipt_row = QHBoxLayout()
        receipt_row.addStretch()
        receipt_row.addWidget(receipt)
        receipt_row.addStretch()
        body_layout.addLayout(receipt_row)

        # Suggested payment, shown independently of the status banner below.
        self.suggestion_banner = StatusBanner()
        body_layout.addWidget(self.suggestion_banner)

        # Payment status
        self.status_banner = StatusBanner()
        body_layout.addWidget(self.status_banner)

        # Amount received label
        self.amount_received_label = QLabel("Amount Received: P0.00")
        self.amount_received_label.setAlignment(Qt.AlignCenter)
        self.amount_received_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700; padding: 10px;"
        )
        body_layout.addWidget(self.amount_received_label)

        # Change label
        self.change_label = QLabel("")
        self.change_label.setAlignment(Qt.AlignCenter)
        self.change_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px; font-weight: 700; "
            f"padding: 8px; background-color: {COLORS['bg_subtle']}; border-radius: 6px;"
        )
        body_layout.addWidget(self.change_label)

        self._add_voucher_entry(body_layout)

        # Simulated coins/bills are for SIM_MODE only: on a real kiosk they would be free credit.
        if get_config().sim_mode:
            self._add_simulation_buttons(body_layout)

        body_layout.addStretch(2)

        # Don't set layout here - let the controller handle it
        self.main_layout = main_layout

    def _add_voucher_entry(self, layout):
        """"Use a voucher": a button that reveals a code entry, plus the list
        of Vouchers Applied so far with what each will have left."""
        row = QHBoxLayout()
        row.setSpacing(6)
        self.use_voucher_btn = SecondaryButton("Use a voucher")
        self.use_voucher_btn.setMinimumHeight(44)
        self.use_voucher_btn.clicked.connect(self._show_voucher_input)
        row.addWidget(self.use_voucher_btn)

        self.voucher_input = QLineEdit()
        self.voucher_input.setPlaceholderText("Voucher code (XXXX-XXXX)")
        self.voucher_input.setMaxLength(16)  # room for 'V1:' and a hyphen
        self.voucher_input.setAlignment(Qt.AlignCenter)
        self.voucher_input.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {COLORS['border_strong']}; border-radius: 6px; padding: 6px; "
            f"font-size: {FONT['size_md']}px; color: {COLORS['text']}; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['primary']}; }}"
        )
        self.voucher_input.textEdited.connect(lambda _: self.voucher_entry_activity.emit())
        self.voucher_input.returnPressed.connect(self._submit_voucher)
        self.apply_voucher_btn = PrimaryButton("Apply")
        self.apply_voucher_btn.setMinimumHeight(44)
        self.apply_voucher_btn.clicked.connect(self._submit_voucher)
        row.addWidget(self.voucher_input, 1)
        row.addWidget(self.apply_voucher_btn)
        layout.addLayout(row)

        # The touchscreen has no keyboard, so the code is typed on this keypad.
        self.voucher_keypad = CodeKeypad(self.voucher_input, self._voucher_keys)
        self.voucher_keypad.pressed.connect(self.voucher_entry_activity.emit)
        layout.addWidget(self.voucher_keypad)

        self.voucher_banner = StatusBanner()
        layout.addWidget(self.voucher_banner)

        self.vouchers_label = QLabel("")
        self.vouchers_label.setAlignment(Qt.AlignCenter)
        self.vouchers_label.setWordWrap(True)
        self.vouchers_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; padding: 4px;"
        )
        layout.addWidget(self.vouchers_label)

        # Vouchers checked in the balance popup this session, each with its balance and a
        # button to apply it. Never applied automatically; hidden when there are none.
        self.checked_vouchers_box = QWidget()
        checked_layout = QVBoxLayout(self.checked_vouchers_box)
        checked_layout.setContentsMargins(0, 0, 0, 0)
        checked_layout.setSpacing(6)
        caption = QLabel("Vouchers you checked:")
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px; font-weight: 600;")
        checked_layout.addWidget(caption)
        self.checked_vouchers_row = QHBoxLayout()
        self.checked_vouchers_row.setSpacing(8)
        checked_layout.addLayout(self.checked_vouchers_row)
        self.checked_vouchers_box.hide()
        layout.addWidget(self.checked_vouchers_box)

        self._set_voucher_input_visible(False)

    def _set_voucher_input_visible(self, visible):
        self.voucher_input.setVisible(visible)
        self.apply_voucher_btn.setVisible(visible)
        self.voucher_keypad.setVisible(visible)

    def _show_voucher_input(self):
        self._set_voucher_input_visible(True)
        self.voucher_input.setFocus()
        self.voucher_entry_activity.emit()

    def _submit_voucher(self):
        text = self.voucher_input.text()
        self.voucher_input.clear()  # don't leave a code sitting on screen
        if text.strip():
            self.voucher_code_entered.emit(text)

    def show_voucher_message(self, message, is_error):
        self.voucher_banner.show_message(message, "error" if is_error else "success")

    def update_vouchers(self, vouchers):
        """vouchers: [AppliedVoucher] in the order Applied."""
        lines = [f"{v.label}: P{v.amount} applied, P{v.remaining} left" for v in vouchers]
        self.vouchers_label.setText("<br>".join(lines))

    def set_checked_vouchers(self, vouchers):
        """vouchers: [CheckedVoucher] not yet applied. One tap-to-apply button each."""
        while self.checked_vouchers_row.count():
            item = self.checked_vouchers_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.checked_vouchers = {}
        for voucher in vouchers:
            button = SecondaryButton(f"Apply {voucher.label}: P{voucher.remaining}")
            button.setMinimumHeight(44)
            button.clicked.connect(lambda _, code=voucher.code: self.checked_voucher_clicked.emit(code))
            self.checked_vouchers_row.addWidget(button)
            self.checked_vouchers[voucher.code] = button
        self.checked_vouchers_box.setVisible(bool(vouchers))

    def reset_voucher_entry(self):
        self.voucher_input.clear()
        self._set_voucher_input_visible(False)
        self.voucher_banner.show_message("", "info")

    def _add_simulation_buttons(self, layout):
        """Adds on-screen coin and bill buttons for SIM_MODE testing."""
        sim_banner = StatusBanner()
        sim_banner.show_message("Simulation Mode - Test Payment", "warning")
        layout.addWidget(sim_banner)

        sim_layout = QHBoxLayout()
        sim_layout.setSpacing(10)

        for val in [1, 5, 10, 20, 50, 100]:
            btn = SecondaryButton(f"P{val}")
            btn.setMinimumSize(44, 44)
            if val <= 10:
                btn.clicked.connect(lambda _, v=val: self.simulation_coin_clicked.emit(v))
            else:
                btn.clicked.connect(lambda _, v=val: self.simulation_bill_clicked.emit(v))
            sim_layout.addWidget(btn)

        layout.addLayout(sim_layout)

    def _set_total(self, total_cost):
        """Total as one row: label on the left, big amount on the right."""
        self.total_label.setText(
            f'<table width="100%"><tr>'
            f'<td valign="middle" style="font-size:{FONT["size_lg"]}px; font-weight:600;">Total Amount Due</td>'
            f'<td align="right" valign="middle" style="font-size:{FONT["size_xl"]}px; font-weight:700;">P{total_cost:.2f}</td>'
            f'</tr></table>'
        )
        self.total_label.setStyleSheet(f"color: {COLORS['text']};")

    @staticmethod
    def _receipt_row(label, value, strong=False):
        weight = 700 if strong else 400
        return (
            f'<tr><td style="color:{COLORS["text_secondary"]};">{label}</td>'
            f'<td align="right" style="font-weight:{weight};">{value}</td></tr>'
        )

    def update_payment_data(self, summary_data):
        """Updates the payment data display."""
        self._set_total(summary_data['total_cost'])

        row = self._receipt_row
        document = escape(str(summary_data['document_name']))
        if summary_data.get('print_job', True):
            title = "Print Job Summary"
            rows = [
                row("Document", document, strong=True),
                row("Copies", f"{summary_data['copies']}"),
                row("Color mode", escape(str(summary_data['color_mode']))),
            ]
            if summary_data['black_pages'] or not summary_data['color_pages']:
                rows.append(row("B&amp;W pages", f"{summary_data['black_pages']}"))
            if summary_data['color_pages']:
                rows.append(row("Color pages", f"{summary_data['color_pages']}"))
        else:
            title = "Digital Copy"
            rows = [
                row("Document", document, strong=True),
                row("Delivery", "Download or email after paying"),
            ]
        if summary_data.get('digital_fee'):
            rows.append(row("Digital copy fee", f"P{summary_data['digital_fee']:.2f}", strong=True))

        self.summary_label.setText(
            f'<div style="font-size:{FONT["size_lg"]}px; font-weight:700; margin-left:3px;">{title}</div>'
            f'<table width="100%" cellspacing="0" cellpadding="3">{"".join(rows)}</table>'
        )

    def update_payment_status(self, status_text):
        """Updates the payment status banner."""
        self.status_banner.show_message(status_text, _classify_status_variant(status_text))

    def update_amount_received(self, amount):
        """Updates the amount received display."""
        self.amount_received_label.setText(f"Amount Received: P{amount:.2f}")

    def update_change_display(self, change_amount, change_text):
        """Updates the change display."""
        self.change_label.setText(change_text)
        if "Remaining" in change_text:
            color, bg = COLORS["danger"], COLORS["danger_bg"]
        else:
            color, bg = COLORS["success"], COLORS["success_bg"]
        self.change_label.setStyleSheet(
            f"color: {color}; font-size: {FONT['size_lg']}px; font-weight: 700; "
            f"padding: 8px; background-color: {bg}; border-radius: 6px;"
        )

    def set_buttons_enabled(self, back_enabled):
        """Sets the enabled state of all buttons."""
        self.back_btn.setEnabled(back_enabled)
        self.use_voucher_btn.setEnabled(back_enabled)
        self.apply_voucher_btn.setEnabled(back_enabled)
        self.voucher_keypad.setEnabled(back_enabled)

    def update_inline_suggestion(self, text: str):
        self.suggestion_banner.show_message(text or "", "info")
