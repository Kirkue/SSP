from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QPushButton, QLabel, QDialogButtonBox)
from PyQt5.QtCore import Qt, pyqtSignal

class PinDialogView(QDialog):
    """View for the PIN Dialog - handles UI components and presentation."""
    
    # Signals for user interactions
    number_clicked = pyqtSignal(str)  # digit
    clear_clicked = pyqtSignal()
    enter_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Access")
        self.setFixedSize(320, 450)
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the user interface for the dialog."""
        self.setStyleSheet(self.get_dialog_style())

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # --- Display for the PIN ---
        self.pin_display = QLabel()
        self.pin_display.setAlignment(Qt.AlignCenter)
        self.pin_display.setMinimumHeight(50)
        self.pin_display.setStyleSheet(self.get_pin_display_style())
        
        # --- Status Label for messages ---
        self.status_label = QLabel("Enter PIN")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; color: #36454F;")

        main_layout.addWidget(self.pin_display)
        main_layout.addWidget(self.status_label)

        # --- Keypad Layout ---
        keypad_layout = QGridLayout()
        keypad_layout.setSpacing(10)
        
        buttons = [
            '1', '2', '3',
            '4', '5', '6',
            '7', '8', '9',
            'C', '0', '✓'
        ]
        
        positions = [(i, j) for i in range(4) for j in range(3)]

        for position, value in zip(positions, buttons):
            button = QPushButton(value)
            if value.isdigit():
                button.clicked.connect(lambda _, v=value: self.number_clicked.emit(v))
            elif value == 'C':
                button.setStyleSheet(self.get_clear_button_style())
                button.clicked.connect(self.clear_clicked.emit)
            elif value == '✓':
                button.setStyleSheet(self.get_enter_button_style())
                button.clicked.connect(self.enter_clicked.emit)
            
            keypad_layout.addWidget(button, *position)

        main_layout.addLayout(keypad_layout)
    
    def update_pin_display(self, pin_text):
        """Updates the PIN display with the provided text (asterisks)."""
        self.pin_display.setText(pin_text)
    
    def update_status(self, status_text):
        """Updates the status label with the provided message."""
        self.status_label.setText(status_text)
    
    def get_dialog_style(self):
        """Returns the main dialog style."""
        return """
            QDialog {
                background-color: white;
                border: 4px solid #d9d9d9;
                border-radius: 10px;
            }
            QLabel {
                color: #36454F;
                font-size: 18px;
            }
            QPushButton {
                background-color: white;
                color: #36454F; /* match 'TOUCH SCREEN TO START' */
                font-size: 24px;
                font-weight: bold;
                border: 2px solid #d9d9d9; /* thinner border */
                border-radius: 8px;
                min-height: 60px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """
    
    def get_pin_display_style(self):
        """Returns the PIN display style."""
        return """
            QLabel {
                background-color: white;
                border: 4px solid #d9d9d9; /* updated border color */
                border-radius: 8px;
                font-size: 32px;
                padding: 5px;
                color: #36454F;
            }
        """
    
    def get_clear_button_style(self):
        """Returns the clear button style."""
        return """
            QPushButton {
                background-color: white;
                color: #36454F; /* match idle text color */
                border: 2px solid #d9d9d9;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border: 2px solid #d9d9d9;
            }
        """
    
    def get_enter_button_style(self):
        """Returns the enter button style."""
        return """
            QPushButton {
                background-color: white;
                color: #36454F; /* match idle text color */
                border: 2px solid #d9d9d9; /* thinner border */
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border: 2px solid #d9d9d9;
            }
        """
