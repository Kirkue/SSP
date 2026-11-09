from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QPushButton, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal

from ui.theme import COLORS, FONT, RADIUS


class PinDialogView(QDialog):
    """View for the PIN Dialog - handles UI components and presentation."""

    # Signals for user interactions
    number_clicked = pyqtSignal(str)  # digit
    clear_clicked = pyqtSignal()
    enter_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Access")
        self.setFixedSize(460, 640)
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the dialog."""
        self.setStyleSheet(self._dialog_qss())

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(18)
        main_layout.setContentsMargins(28, 28, 28, 28)

        # --- Display for the PIN ---
        self.pin_display = QLabel()
        self.pin_display.setObjectName("PinDisplay")
        self.pin_display.setAlignment(Qt.AlignCenter)
        self.pin_display.setMinimumHeight(72)

        # --- Status Label for messages ---
        self.status_label = QLabel("Enter PIN")
        self.status_label.setObjectName("PinStatus")
        self.status_label.setAlignment(Qt.AlignCenter)

        main_layout.addWidget(self.pin_display)
        main_layout.addWidget(self.status_label)

        # --- Keypad Layout ---
        keypad_layout = QGridLayout()
        keypad_layout.setSpacing(14)

        buttons = [
            '1', '2', '3',
            '4', '5', '6',
            '7', '8', '9',
            'C', '0', '✓'
        ]

        self._keys = []
        positions = [(i, j) for i in range(4) for j in range(3)]

        for position, value in zip(positions, buttons):
            button = QPushButton(value)
            button.setCursor(Qt.PointingHandCursor)
            if value.isdigit():
                button.clicked.connect(lambda _, v=value: self.number_clicked.emit(v))
            elif value == 'C':
                button.setObjectName("PinClear")
                button.clicked.connect(self.clear_clicked.emit)
            elif value == '✓':
                button.setObjectName("PinEnter")
                button.clicked.connect(self.enter_clicked.emit)

            self._keys.append(button)
            keypad_layout.addWidget(button, *position)

        main_layout.addLayout(keypad_layout)

    def update_pin_display(self, pin_text):
        """Updates the PIN display with the provided text (asterisks)."""
        self.pin_display.setText(pin_text)

    def set_locked(self, locked, seconds):
        """Disables the keypad and shows the time left while locked."""
        was_locked = not self._keys[0].isEnabled()
        for key in self._keys:
            key.setEnabled(not locked)
        if locked:
            self.status_label.setText(f"Locked. Try again in {seconds // 60}:{seconds % 60:02d}")
        elif was_locked:
            self.status_label.setText("Enter PIN")

    def update_status(self, status_text):
        """Updates the status label with the provided message."""
        self.status_label.setText(status_text)

    def _dialog_qss(self):
        return f"""
            QDialog {{
                background-color: {COLORS['bg']};
                border: 1px solid {COLORS['border_strong']};
                border-radius: {RADIUS['lg']}px;
            }}
            QLabel#PinDisplay {{
                background-color: {COLORS['bg_subtle']};
                border: 1px solid {COLORS['border_strong']};
                border-radius: {RADIUS['md']}px;
                font-size: {FONT['size_display']}px;
                font-weight: 700;
                letter-spacing: 6px;
                color: {COLORS['text']};
            }}
            QLabel#PinStatus {{
                font-size: {FONT['size_sm']}px;
                color: {COLORS['text_secondary']};
            }}
            QPushButton {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
                font-size: {FONT['size_xl']}px;
                font-weight: 600;
                border: 1px solid {COLORS['border_strong']};
                border-radius: {RADIUS['md']}px;
                min-height: 76px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_subtle']};
                border-color: {COLORS['primary']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['border']};
            }}
            QPushButton#PinClear {{
                color: {COLORS['text_secondary']};
            }}
            QPushButton#PinEnter {{
                background-color: {COLORS['primary']};
                color: {COLORS['bg']};
                border: none;
            }}
            QPushButton#PinEnter:hover {{
                background-color: {COLORS['primary_hover']};
            }}
            QPushButton#PinEnter:pressed {{
                background-color: {COLORS['primary_pressed']};
            }}
        """
