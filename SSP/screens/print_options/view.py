# screens/print_options/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QStackedLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

class PrintOptionsScreenView(QWidget):
    """The user interface for the Print Options Screen. Contains no logic."""
    back_button_clicked = pyqtSignal()
    continue_button_clicked = pyqtSignal()
    bw_mode_clicked = pyqtSignal()
    color_mode_clicked = pyqtSignal()
    copies_decreased = pyqtSignal()
    copies_increased = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Sets up the user interface components."""
        stacked_layout = QStackedLayout(self)
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setStackingMode(QStackedLayout.StackAll)

        # Background Layer
        self.background_label = QLabel()
        self._load_background_image()

        # Foreground Layer
        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(foreground_widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)

        layout.addStretch(1)

        # === Centered Container for Color Mode and Number of Copies ===
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(24)
        center_layout.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        # ---- Number of Copies Row ----
        copies_row = QHBoxLayout()
        copies_row.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        copies_label = QLabel("Number of Copies:")
        copies_label.setStyleSheet("color: #36454F; font-size: 18px; font-weight: bold; background-color: transparent;")
        copies_row.addWidget(copies_label)

        self.copies_minus_btn = QPushButton("−")
        self.copies_plus_btn = QPushButton("+")
        self.copies_minus_btn.setStyleSheet(self.get_copies_button_style())
        self.copies_plus_btn.setStyleSheet(self.get_copies_button_style())
        self.copies_minus_btn.setFixedSize(44, 44)
        self.copies_plus_btn.setFixedSize(44, 44)
        self.copies_minus_btn.clicked.connect(self.copies_decreased.emit)
        self.copies_plus_btn.clicked.connect(self.copies_increased.emit)
        
        copies_row.addSpacing(20)
        copies_row.addWidget(self.copies_minus_btn)

        self.copies_count_label = QLabel("1")
        self.copies_count_label.setStyleSheet(self.get_copies_label_style())
        self.copies_count_label.setAlignment(Qt.AlignCenter)
        copies_row.addWidget(self.copies_count_label)
        copies_row.addWidget(self.copies_plus_btn)
        copies_row.addStretch(1)
        center_layout.addLayout(copies_row)

        # ---- Color Mode Row ----
        color_row = QHBoxLayout()
        color_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        color_label = QLabel("Color Mode:")
        color_label.setStyleSheet("color: #36454F; font-size: 18px; font-weight: bold; background-color: transparent;")
        color_row.addWidget(color_label)
        color_row.addStretch(1)

        self.bw_btn = QPushButton("Black and White")
        self.color_btn = QPushButton("Colored")
        self.bw_btn.setCheckable(True)
        self.color_btn.setCheckable(True)
        self.bw_btn.setStyleSheet(self.get_color_button_style())
        self.color_btn.setStyleSheet(self.get_color_button_style())
        self.bw_btn.setChecked(True)
        
        self.bw_btn.clicked.connect(self.bw_mode_clicked.emit)
        self.color_btn.clicked.connect(self.color_mode_clicked.emit)
        
        color_row.addWidget(self.bw_btn)
        color_row.addSpacing(8)
        color_row.addWidget(self.color_btn)
        center_layout.addLayout(color_row)

        # Add centered container to the main layout
        layout.addWidget(center_container, 0, Qt.AlignHCenter)

        # Add more space below the centered container before cost/details.
        layout.addSpacing(60)

        # ---- Cost and Details ----
        self.cost_label = QLabel("Calculating cost...")
        self.cost_label.setAlignment(Qt.AlignCenter)
        self.cost_label.setStyleSheet("color: #33cc33; font-size: 24px; font-weight: bold; margin: 0px 0 0 0;")
        layout.addWidget(self.cost_label, 0, Qt.AlignHCenter)

        self.analysis_details_label = QLabel("Analysis details will appear here.")
        self.analysis_details_label.setAlignment(Qt.AlignCenter)
        self.analysis_details_label.setStyleSheet("color: #36454F; font-size: 14px; margin-top: 5px;")
        layout.addWidget(self.analysis_details_label, 0, Qt.AlignHCenter)

        layout.addStretch(2)

        # ---- Buttons ----
        buttons_layout = QHBoxLayout()
        self.back_btn = QPushButton("← Back to File Browser")
        self.back_btn.setMinimumHeight(50)
        self.back_btn.setStyleSheet(self.get_back_button_style())

        self.continue_btn = QPushButton("Continue to Payment →")
        self.continue_btn.setMinimumHeight(50)
        self.continue_btn.setStyleSheet(self.get_continue_button_style())

        self.back_btn.clicked.connect(self.back_button_clicked.emit)
        self.continue_btn.clicked.connect(self.continue_button_clicked.emit)

        buttons_layout.addWidget(self.back_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.continue_btn)
        layout.addLayout(buttons_layout)

        stacked_layout.addWidget(self.background_label)
        stacked_layout.addWidget(foreground_widget)
        # Don't set layout here - let the controller handle it
        self.main_layout = stacked_layout
    
    def _load_background_image(self):
        """Loads the background image."""
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'print_options_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.background_label.setPixmap(pixmap)
            self.background_label.setScaledContents(True)
        else:
            print(f"WARNING: Background image not found at '{image_path}'.")
            self.background_label.setStyleSheet("background-color: #1f1f38;")
    
    def update_copies_display(self, copies):
        """Updates the copies count display."""
        self.copies_count_label.setText(str(copies))
    
    def set_bw_mode(self):
        """Sets the black and white mode as selected."""
        self._color_mode = "Black and White"
        self.bw_btn.setChecked(True)
        self.color_btn.setChecked(False)
    
    def set_color_mode(self):
        """Sets the color mode as selected."""
        self._color_mode = "Color"
        self.bw_btn.setChecked(False)
        self.color_btn.setChecked(True)
    
    def update_cost_display(self, cost_text, details_text):
        """Updates the cost and details display."""
        self.cost_label.setText(cost_text)
        self.analysis_details_label.setText(details_text)
    
    def set_analysis_status(self, status_text, details_text):
        """Sets the analysis status display."""
        self.cost_label.setText(status_text)
        self.analysis_details_label.setText(details_text)
    
    def set_continue_button_enabled(self, enabled):
        """Enables or disables the continue button."""
        self.continue_btn.setEnabled(enabled)
    
    def show_paper_warning(self, available_paper, required_paper):
        """Shows a warning about insufficient paper."""
        warning_text = f"⚠️ INSUFFICIENT PAPER ⚠️"
        details_text = f"Only {available_paper} sheets available, but {required_paper} sheets needed.\nPlease contact administrator to refill paper."
        
        # Update the display with warning
        self.cost_label.setText(warning_text)
        self.cost_label.setStyleSheet("color: #dc3545; font-size: 24px; font-weight: bold; margin: 0px 0 0 0;")
        self.analysis_details_label.setText(details_text)
        self.analysis_details_label.setStyleSheet("color: #dc3545; font-size: 14px; margin-top: 5px; font-weight: bold;")
        
        # Disable the continue button
        self.continue_btn.setEnabled(False)
        self.continue_btn.setText("❌ Insufficient Paper")
        self.continue_btn.setStyleSheet("""
            QPushButton {
                color: white; font-size: 12px; font-weight: bold;
                border: none; border-radius: 4px !important; height: 40px;
                background-color: #dc3545;
                padding-left: 12px; padding-right: 12px;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
    
    def clear_paper_warning(self):
        """Clears the paper warning and resets the display."""
        # Reset the continue button
        self.continue_btn.setEnabled(True)
        self.continue_btn.setText("Continue to Payment →")
        self.continue_btn.setStyleSheet(self.get_continue_button_style())
        
        # Reset the cost label style
        self.cost_label.setStyleSheet("color: #33cc33; font-size: 24px; font-weight: bold; margin: 0px 0 0 0;")
        self.analysis_details_label.setStyleSheet("color: #36454F; font-size: 14px; margin-top: 5px;")
    
    def get_copies_button_style(self):
        """Returns the style for copy control buttons."""
        return """
            QPushButton {
                background-color: #1e440a; color: #fff; border: none; border-radius: 4px;
                font-size: 22px; width: 44px; height: 44px; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
                padding: 0; font-weight: bold;
            }
            QPushButton:pressed, QPushButton:checked, QPushButton:hover { background-color: #2a5d1a; }
        """
    
    def get_copies_label_style(self):
        """Returns the style for the copies count label."""
        return """
            QLabel { 
                background-color: transparent; color: #36454F; font-size: 22px; 
                min-width: 40px; max-width: 40px; border-radius: 3px; padding: 1px 4px; 
                border: none; font-weight: bold; qproperty-alignment: AlignCenter; 
            }
        """
    
    def get_color_button_style(self):
        """Returns the style for color mode buttons."""
        return """
            QPushButton {
                color: white; font-size: 16px; font-weight: bold;
                border: none; border-radius: 4px !important; height: 44px; min-width: 130px;
                background-color: #1e440a;
                padding-left: 12px; padding-right: 12px;
            }
            QPushButton:checked, QPushButton:hover { background-color: #2a5d1a; }
        """
    
    def get_back_button_style(self):
        """Returns the style for the back button."""
        return """
            QPushButton {
                color: white; font-size: 12px; font-weight: bold;
                border: none; border-radius: 4px; height: 40px;
                background-color: #ff0000;
                padding-left: 12px; padding-right: 12px;
            }
            QPushButton:hover { background-color: #ffb84d; }
        """
    
    def get_continue_button_style(self):
        """Returns the style for the continue button."""
        return """
            QPushButton {
                color: white; font-size: 12px; font-weight: bold;
                border: none; border-radius: 4px !important; height: 40px;
                background-color: #1e440a;
                padding-left: 12px; padding-right: 12px;
            }
            QPushButton:checked, QPushButton:hover { background-color: #2a5d1a; }
        """
