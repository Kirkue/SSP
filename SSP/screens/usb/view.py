# screens/usb/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedLayout,
    QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QColor

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

class USBScreenView(QWidget):
    """The user interface for the USB Screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.blink_timer = QTimer(self)
        self.setup_ui()
        self.setup_timers()
    
    def setup_ui(self):
        """Initializes the user interface using a flexible, layered layout."""
        # 1. Main Stacked Layout for Background/Foreground Layering
        main_layout = QStackedLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        self.setLayout(main_layout)

        # 2. Background Layer
        self.background_label = QLabel()
        self._load_background_image()

        # 3. Foreground Layer (contains all UI controls)
        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")
        
        fg_layout = QVBoxLayout(foreground_widget)
        fg_layout.setContentsMargins(40, 30, 40, 30)
        fg_layout.setSpacing(15)

        # --- UI Elements ---
        title = QLabel("INSERT USB FLASHDRIVE")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #36454F; font-size: 38px; font-weight: bold;")
        title.setWordWrap(True)

        instruction = QLabel("The system will automatically detect your drive.")
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setWordWrap(True)
        instruction.setStyleSheet("color: #36454F; font-size: 22px; line-height: 1.4;")
        instruction.setMaximumWidth(800)

        self.status_indicator = QLabel("Initializing...")
        self.status_indicator.setAlignment(Qt.AlignCenter)
        self.status_indicator.setMinimumHeight(55)
        self.status_indicator.setStyleSheet(self.get_initial_status_style())
        
        # Safety warning label (hidden by default)
        self.safety_warning = QLabel("")
        self.safety_warning.setAlignment(Qt.AlignCenter)
        self.safety_warning.setMinimumHeight(40)
        self.safety_warning.setStyleSheet("""
            QLabel {
                color: #dc3545; font-size: 16px; font-weight: bold;
                padding: 8px 16px; border: 2px solid #dc3545; border-radius: 6px;
                background-color: rgba(220, 53, 69, 0.1);
            }
        """)
        self.safety_warning.hide()

        # Button Creation
        self.back_button = QPushButton("← Back to Main")
        self.back_button.setStyleSheet(self.get_back_button_style())
        
        # --- Layout Assembly ---
        fg_layout.addStretch(3)
        fg_layout.addWidget(title, 0, Qt.AlignCenter)
        fg_layout.addSpacing(10)
        fg_layout.addWidget(instruction, 0, Qt.AlignCenter)
        fg_layout.addStretch(1)
        
        status_layout = QHBoxLayout()
        status_layout.addStretch()
        status_layout.addWidget(self.status_indicator)
        status_layout.addStretch()
        fg_layout.addLayout(status_layout)
        
        # Add safety warning layout
        safety_layout = QHBoxLayout()
        safety_layout.addStretch()
        safety_layout.addWidget(self.safety_warning)
        safety_layout.addStretch()
        fg_layout.addLayout(safety_layout)
        
        fg_layout.addSpacing(20)
        fg_layout.addStretch(4)

        nav_buttons_layout = QHBoxLayout()
        nav_buttons_layout.addWidget(self.back_button, 0, Qt.AlignLeft)
        nav_buttons_layout.addStretch()
        fg_layout.addLayout(nav_buttons_layout)

        # 4. Add Layers to Main Layout
        main_layout.addWidget(self.background_label)
        main_layout.addWidget(foreground_widget)
        
        # Set the foreground widget as the active one for interaction
        main_layout.setCurrentWidget(foreground_widget)

        # Connect button signals
        self.back_button.clicked.connect(self.back_button_clicked.emit)
    
    def setup_timers(self):
        """Sets up timers for the view."""
        self.blink_timer.timeout.connect(self.blink_status)
    
    def _load_background_image(self):
        """Loads the background image."""
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'usb_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'")
            self.background_label.setStyleSheet("background-color: #e0e0e0;")
    
    def update_status_indicator(self, text, style_key, color_hex):
        """Updates the text and style of the status indicator label."""
        self.status_indicator.setText(text)
        self.status_indicator.setStyleSheet(f"""
            QLabel {{
                color: {color_hex}; font-size: 18px; font-weight: bold;
                padding: 10px 20px; border: 2px solid {color_hex}; border-radius: 8px;
                background-color: rgba({QColor(color_hex).red()}, {QColor(color_hex).green()}, {QColor(color_hex).blue()}, 0.1);
            }}""")
    
    def blink_status(self):
        """Toggles the opacity of the status indicator for a blinking effect."""
        current_style = self.status_indicator.styleSheet()
        if "0.1" in current_style:
            new_style = current_style.replace("0.1", "0.05")
        else:
            new_style = current_style.replace("0.05", "0.1")
        self.status_indicator.setStyleSheet(new_style)
    
    def start_blinking(self):
        """Starts the blinking effect."""
        self.blink_timer.start(700)
    
    def stop_blinking(self):
        """Stops the blinking effect."""
        self.blink_timer.stop()
    
    
    def show_message(self, title, text):
        """Shows a message to the user."""
        QMessageBox.information(self, title, text)
    
    def show_warning(self, title, text):
        """Shows a warning message to the user."""
        QMessageBox.warning(self, title, text)
    
    def get_initial_status_style(self):
        """Returns the initial style for the status indicator."""
        return """
            QLabel {
                color: #555; font-size: 18px; padding: 10px 20px;
                border: 2px solid #ccc; border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.1);
            }"""


    def get_back_button_style(self):
        """Returns the style for the back button."""
        return """
            QPushButton { 
                background-color: #6c757d; color: white; font-size: 14px;
                border: none; border-radius: 6px; padding: 10px 20px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """
    
    def show_safety_warning(self, message):
        """Shows a safety warning message."""
        self.safety_warning.setText(message)
        self.safety_warning.show()
    
    def hide_safety_warning(self):
        """Hides the safety warning message."""
        self.safety_warning.hide()

