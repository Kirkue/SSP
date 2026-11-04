# screens/landing/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.icons import icon
from ui.theme import COLORS, FONT
from ui.widgets import Card, Header, LowChangeBanner, ReaderHint, SecondaryButton, StatusBanner


class HomepageScreenView(QWidget):
    """The user interface for the Landing (upload method selection) screen. Contains no logic."""

    method_card_clicked = pyqtSignal(str)  # method_key
    voucher_balance_clicked = pyqtSignal()
    admin_button_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        fg_layout = QVBoxLayout(content)
        fg_layout.setContentsMargins(120, 24, 120, 0)
        fg_layout.setSpacing(8)
        outer_layout.addWidget(content, 1)

        # Same entry point as the idle screen, at the same spot (50px from the right
        # edge, 30px from the bottom). PIN-gated by the controller.
        self.admin_button = SecondaryButton("Admin")
        self.admin_button.setIcon(icon('admin'))
        self.admin_button.setFixedSize(100, 36)
        self.admin_button.clicked.connect(self.admin_button_clicked.emit)
        # A widget (not a bare layout) so the strip gets the white fill; otherwise the
        # window's background image shows through beneath the content.
        admin_footer = QWidget()
        admin_footer.setStyleSheet(f"background-color: {COLORS['bg']};")
        admin_row = QHBoxLayout(admin_footer)
        admin_row.setContentsMargins(50, 0, 50, 30)
        admin_row.addStretch(1)
        admin_row.addWidget(self.admin_button)
        outer_layout.addWidget(admin_footer)

        title = QLabel("Select Upload Method")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        subtitle = QLabel("Please select the desired file upload method or the scanning function.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px;")

        disclaimer = QLabel("Disclaimer: This kiosk only accepts files in the PDF format.")
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: {FONT['size_sm']}px; font-weight: 600;")

        self.reader_hint = ReaderHint()
        self.status_banner = StatusBanner()
        self.low_change_banner = LowChangeBanner()

        fg_layout.addStretch(1)
        fg_layout.addWidget(title)
        fg_layout.addSpacing(8)
        fg_layout.addWidget(subtitle)
        fg_layout.addWidget(disclaimer)
        fg_layout.addSpacing(8)
        fg_layout.addWidget(self.reader_hint)
        fg_layout.addWidget(self.status_banner)
        fg_layout.addWidget(self.low_change_banner)
        fg_layout.addStretch(1)

        # Cards: 2x2 grid.
        self.usb_card = Card('usb', "USB", "Upload files via USB.", icon_name='usb')
        self.wifi_card = Card('wifi', "WiFi", 'Connect to the local network:\n"usc_printer_kiosk"', icon_name='wifi')
        self.email_card = Card('email', "Email", "Email address:\nprinter_kiosk@usc.edu.ph", icon_name='email')
        self.scanner_card = Card(
            'scanner', "Scanner", "Scan documents via the printer's built-in scanner.", icon_name='scanner'
        )

        for card in (self.usb_card, self.wifi_card, self.email_card, self.scanner_card):
            card.clicked.connect(self.method_card_clicked.emit)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(20)
        cards_grid.setVerticalSpacing(20)
        cards_grid.addWidget(self.usb_card, 0, 0)
        cards_grid.addWidget(self.wifi_card, 0, 1)
        cards_grid.addWidget(self.email_card, 1, 0)
        cards_grid.addWidget(self.scanner_card, 1, 1)

        grid_wrapper = QHBoxLayout()
        grid_wrapper.addStretch()
        grid_wrapper.addLayout(cards_grid)
        grid_wrapper.addStretch()
        fg_layout.addLayout(grid_wrapper)

        # Not an upload method, so a plain button below the cards rather than a fifth card.
        self.voucher_balance_button = SecondaryButton("Check voucher balance")
        self.voucher_balance_button.clicked.connect(self.voucher_balance_clicked.emit)
        voucher_row = QHBoxLayout()
        voucher_row.addStretch()
        voucher_row.addWidget(self.voucher_balance_button)
        voucher_row.addStretch()
        fg_layout.addSpacing(12)
        fg_layout.addLayout(voucher_row)
        fg_layout.addStretch(2)

    def set_change_low(self, low):
        self.low_change_banner.set_low(low)

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")
