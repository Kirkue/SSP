# ui/timeout_warning.py
"""The "Still there?" prompt (docs/remaining-work.md 2.1).

A full-window overlay, so taps elsewhere can't reach the screen underneath while it's up:
the only way on is its button, which adds time. Shown by main_app when the timeout manager
reports `warning_shown`, and hidden on `warning_hidden`.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

from ui.theme import COLORS, FONT, RADIUS
from ui.widgets import PrimaryButton


class TimeoutWarning(QFrame):
    extend_clicked = pyqtSignal()

    def __init__(self, extend_seconds: int, parent=None):
        super().__init__(parent)
        self.setObjectName("TimeoutWarning")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#TimeoutWarning { background-color: rgba(0, 0, 0, 140); }")

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        self.card = QFrame()
        self.card.setObjectName("TimeoutCard")
        self.card.setFixedWidth(620)
        self.card.setStyleSheet(
            f"QFrame#TimeoutCard {{ background-color: {COLORS['bg']}; border-radius: {RADIUS['lg']}px; }}"
        )
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(12)

        self.title_label = QLabel("Still there?")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_xl']}px; font-weight: 700;"
        )
        layout.addWidget(self.title_label)

        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONT['size_lg']}px; font-weight: 600;"
        )
        layout.addWidget(self.countdown_label)

        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            f"color: {COLORS['text']}; font-size: {FONT['size_md']}px; font-weight: 700;"
        )
        self.message_label.hide()
        layout.addWidget(self.message_label)

        layout.addSpacing(8)
        self.extend_button = PrimaryButton("")
        self.extend_button.setMinimumHeight(64)
        self.extend_button.clicked.connect(self.extend_clicked.emit)
        layout.addWidget(self.extend_button)
        self.set_extend_seconds(extend_seconds)

        self.hide()

    def set_extend_seconds(self, seconds: int):
        self.extend_button.setText(f"Add {seconds} seconds")

    def show_warning(self, seconds_left: int, message: str = ""):
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self.update_remaining(seconds_left)
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def update_remaining(self, seconds_left):
        if seconds_left is None:
            return
        self.countdown_label.setText(f"This screen closes in {seconds_left} s.")

    def hide_warning(self):
        self.hide()
