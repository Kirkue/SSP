# screens/idle/view.py

import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QStackedLayout)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter

class IdleScreenView(QWidget):
    """The user interface for the Idle Screen. Contains no logic."""
    screen_touched = pyqtSignal(object)  # Emits mouse event
    admin_button_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.background_pixmap = None
        self.setup_ui()
        self._load_background_image()

    def _load_background_image(self):
        """
        Constructs the path to the default background image and loads it.
        Assumes the file structure is: SSP/screens/idle/view.py and SSP/assets/
        """
        try:
            # Get the directory of the current script (screens/idle/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Navigate up to the project root (SSP) and then into the assets folder
            image_path = os.path.join(current_dir, '..', '..', 'assets', 'idle_screen background.png')
            # Normalize the path to resolve ".." and ensure OS compatibility
            normalized_path = os.path.normpath(image_path)
            self.set_background_image(normalized_path)
        except Exception as e:
            print(f"ERROR: Could not automatically load background image. {e}")

    def paintEvent(self, event):
        """Custom paint event to draw background image."""
        painter = QPainter(self)
        if self.background_pixmap:
            painter.drawPixmap(self.rect(), self.background_pixmap)
        else:
            # Fallback to a white background if the image fails to load
            painter.fillRect(self.rect(), Qt.white)
        super().paintEvent(event)
    
    def setup_ui(self):
        """Sets up the user interface components."""
        # --- THEME COLORS ---
        COLOR_BACKGROUND = "#FFFFFF"
        COLOR_PRIMARY_GREEN = "#006837"
        COLOR_LIGHT_GRAY_TEXT = "#666666"

        main_layout = QStackedLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setStackingMode(QStackedLayout.StackAll)
        
        # Background layer (handled by paintEvent)
        background_widget = QWidget()
        background_widget.setStyleSheet("background-color: transparent;")

        # Foreground frame with content
        foreground_frame = QFrame()
        foreground_frame.setStyleSheet("background-color: transparent;")
        
        frame_layout = QVBoxLayout(foreground_frame)
        frame_layout.setContentsMargins(50, 50, 50, 30)
        frame_layout.setSpacing(10)
        
        # --- "Touch to Start" Label ---
        self.touch_to_start_label = QLabel("TOUCH SCREEN TO START")
        self.touch_to_start_label.setAlignment(Qt.AlignCenter)
        self.touch_to_start_label.setStyleSheet("color: #36454F; font-size: 52px; font-weight: bold; padding: 20px;")
        
        # --- Supported Formats Label ---
        self.bottom_info = QLabel("Supported Format: PDF Files Only")
        self.bottom_info.setAlignment(Qt.AlignCenter)
        self.bottom_info.setStyleSheet("color: #36454F; font-size: 16px;")

        # --- Layout Adjustments for Centering ---
        frame_layout.addStretch(2) 
        frame_layout.addWidget(self.touch_to_start_label)
        frame_layout.addWidget(self.bottom_info)
        frame_layout.addStretch(2) 
        
        # --- Admin Button ---
        self.admin_button = QPushButton("Admin")
        self.admin_button.setFixedSize(90, 35)
        self.admin_button.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLOR_BACKGROUND};"
            f"  color: {COLOR_LIGHT_GRAY_TEXT};"
            f"  font-size: 13px;"
            f"  border: 1px solid #CCCCCC;"
            f"  border-radius: 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #f0f0f0;"
            f"  color: {COLOR_PRIMARY_GREEN};"
            f"  border-color: {COLOR_PRIMARY_GREEN};"
            f"}}"
        )
        self.admin_button.clicked.connect(self.admin_button_clicked.emit)
        
        admin_layout = QHBoxLayout()
        admin_layout.addStretch(1)
        admin_layout.addWidget(self.admin_button)
        frame_layout.addLayout(admin_layout)

        main_layout.addWidget(background_widget)
        main_layout.addWidget(foreground_frame)
        
        self.setLayout(main_layout)
    
    def mousePressEvent(self, event):
        """Handles mouse press events and emits signal."""
        self.screen_touched.emit(event)
    
    def set_background_image(self, image_path):
        """Sets the background image from the provided path."""
        if os.path.exists(image_path):
            self.background_pixmap = QPixmap(image_path)
            self.update()  # Trigger repaint
        else:
            print(f"WARNING: Background image not found at '{image_path}'.")
    
    def get_admin_button_geometry(self):
        """Returns the geometry of the admin button for touch validation."""
        return self.admin_button.geometry()