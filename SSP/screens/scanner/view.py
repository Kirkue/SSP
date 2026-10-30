# screens/scanner/view.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from ui.theme import COLORS, FONT
from ui.widgets import BackButton, Card, Header, PrimaryButton, SecondaryButton, StatusBanner, nav_row


# Big enough to read a page's text before tapping Done; A4-shaped, and short
# enough to fit above the bottom nav row on an 800px-tall screen.
PREVIEW_WIDTH = 380
PREVIEW_HEIGHT = 520
PREVIEW_PLACEHOLDER = "Your scanned page will appear here."


class ScannerScreenView(QWidget):
    """The user interface for the Scanner screen. Contains no logic."""
    cancel_clicked = pyqtSignal()
    scan_page_clicked = pyqtSignal()
    rescan_clicked = pyqtSignal()
    done_clicked = pyqtSignal()
    colour_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._has_pages = False
        self.setup_ui()

    def setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        outer_layout.addWidget(Header())

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg']};")
        body_layout = QVBoxLayout(content)
        body_layout.setContentsMargins(60, 16, 60, 24)
        body_layout.setSpacing(8)
        outer_layout.addWidget(content, 1)

        self.cancel_button = BackButton("Cancel Scan")
        self.cancel_button.clicked.connect(self.cancel_clicked.emit)

        # Two columns: instructions and the Scan card on the left (read first), the
        # latest page large on the right so customers can check it before Done.
        columns = QHBoxLayout()
        columns.setSpacing(40)
        body_layout.addLayout(columns, 1)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        columns.addLayout(left_column, 1)

        left_column.addStretch(1)

        guide_title = QLabel("Usage Guide")
        guide_title.setAlignment(Qt.AlignCenter)
        guide_title.setStyleSheet(f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;")

        guide_text = QLabel(
            '1. Place your document face-down on the scanner glass, then tap "Scan Page".<br>'
            '2. Not happy with a page? Tap "Rescan Last Page" to redo it.<br>'
            '3. Repeat for each page of a multi-page document, then tap "Done".'
        )
        guide_text.setAlignment(Qt.AlignCenter)
        guide_text.setWordWrap(True)
        guide_text.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px;")

        self.page_count_label = QLabel("No pages scanned yet")
        self.page_count_label.setAlignment(Qt.AlignCenter)
        self.page_count_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_lg']}px; font-weight: 700;"
        )

        left_column.addWidget(guide_title)
        left_column.addSpacing(6)
        left_column.addWidget(guide_text)
        left_column.addSpacing(16)
        left_column.addWidget(self.page_count_label)
        left_column.addSpacing(10)

        self.scan_card = Card('scan', "Scan Page", "Tap to scan the next page.", icon_name='scanner')
        self.scan_card.clicked.connect(lambda _key: self.scan_page_clicked.emit())

        cards_row = QHBoxLayout()
        cards_row.addStretch()
        cards_row.addWidget(self.scan_card)
        cards_row.addStretch()
        left_column.addLayout(cards_row)

        # Greyscale is the default because it scans about twice as fast; the cost of
        # switching to colour is stated on the button.
        self.colour_button = SecondaryButton("")
        self.colour_button.setCheckable(True)
        self.colour_button.toggled.connect(self._on_colour_toggled)
        colour_row = QHBoxLayout()
        colour_row.addStretch()
        colour_row.addWidget(self.colour_button)
        colour_row.addStretch()
        left_column.addSpacing(8)
        left_column.addLayout(colour_row)
        self._update_colour_text(False)

        left_column.addSpacing(8)

        # eSCL reports no real progress, so this is paced against how long recent scans took.
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {COLORS['bg_subtle']}; border: 1px solid {COLORS['border_strong']};"
            f" border-radius: 6px; }}"
            f"QProgressBar::chunk {{ background-color: {COLORS['primary']}; border-radius: 5px; }}"
        )
        self.progress_bar.hide()
        left_column.addWidget(self.progress_bar)

        left_column.addSpacing(8)

        self.status_banner = StatusBanner()
        left_column.addWidget(self.status_banner)

        left_column.addStretch(2)

        right_column = QVBoxLayout()
        right_column.setSpacing(8)
        columns.addLayout(right_column)

        right_column.addStretch(1)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            f"background-color: {COLORS['bg_subtle']}; border: 1px solid {COLORS['border_strong']};"
            f" border-radius: 8px; color: {COLORS['text_muted']}; font-size: {FONT['size_md']}px;"
        )
        right_column.addWidget(self.preview_label)

        self.preview_caption = QLabel("")
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_md']}px; font-weight: 600;"
        )
        right_column.addWidget(self.preview_caption)

        right_column.addStretch(1)

        self.rescan_button = SecondaryButton("Rescan Last Page")
        self.rescan_button.clicked.connect(self.rescan_clicked.emit)
        self.rescan_button.setEnabled(False)

        self.done_button = PrimaryButton("Done")
        self.done_button.clicked.connect(self.done_clicked.emit)
        self.done_button.setEnabled(False)

        body_layout.addLayout(nav_row(self.cancel_button, self.rescan_button, self.done_button))

    def show_status(self, message, is_error=True):
        self.status_banner.show_message(message, variant="error" if is_error else "success")

    def _update_colour_text(self, colour: bool):
        self.colour_button.setText("Colour: on (slower)" if colour else "Colour: off (faster)")

    def _on_colour_toggled(self, colour: bool):
        self._update_colour_text(colour)
        self.colour_toggled.emit(colour)

    def set_colour(self, colour: bool):
        """Shows the current mode without announcing it as a change."""
        self.colour_button.blockSignals(True)
        self.colour_button.setChecked(colour)
        self.colour_button.blockSignals(False)
        self._update_colour_text(colour)

    def show_progress(self, fraction: float):
        self.progress_bar.setValue(int(round(max(0.0, min(1.0, fraction)) * 100)))
        self.progress_bar.show()

    def hide_progress(self):
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

    def set_busy(self, busy: bool):
        self.colour_button.setEnabled(not busy)
        self.scan_card.setEnabled(not busy)
        self.rescan_button.setEnabled(not busy and self._has_pages)
        self.done_button.setEnabled(not busy and self._has_pages)

    def update_page_count(self, count: int):
        self._has_pages = count > 0
        if count == 0:
            self.page_count_label.setText("No pages scanned yet")
        elif count == 1:
            self.page_count_label.setText("1 page scanned")
        else:
            self.page_count_label.setText(f"{count} pages scanned")
        self.rescan_button.setEnabled(self._has_pages)
        self.done_button.setEnabled(self._has_pages)

    def show_preview(self, image_path: str, page_number: int):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        inner = self.preview_label.size() - QSize(16, 16)  # keep the page off the border
        self.preview_label.setPixmap(pixmap.scaled(inner, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview_caption.setText(f"Page {page_number}")

    def clear_preview(self):
        self.preview_label.clear()
        self.preview_label.setText(PREVIEW_PLACEHOLDER)
        self.preview_caption.setText("")

    def reset(self, colour: bool = False):
        self.set_colour(colour)
        self.hide_progress()
        self.update_page_count(0)
        self.clear_preview()
        self.show_status("")
        self.set_busy(False)
