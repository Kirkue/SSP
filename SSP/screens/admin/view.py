# screens/admin/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QLineEdit, QMessageBox, QGroupBox, QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QPixmap, QPainter

class AdminScreenView(QWidget):
    """The user interface for the Admin Panel. Contains no logic."""
    back_clicked = pyqtSignal()
    view_data_logs_clicked = pyqtSignal()
    update_paper_clicked = pyqtSignal(str)
    reset_paper_clicked = pyqtSignal()
    update_coin_1_clicked = pyqtSignal(str)
    update_coin_5_clicked = pyqtSignal(str)
    reset_coins_clicked = pyqtSignal()
    update_cmyk_clicked = pyqtSignal(float, float, float, float)
    reset_cmyk_clicked = pyqtSignal()
    refresh_cmyk_clicked = pyqtSignal()
    
    # New signals for +/- button functionality
    paper_decreased = pyqtSignal()
    paper_increased = pyqtSignal()
    coin_1_decreased = pyqtSignal()
    coin_1_increased = pyqtSignal()
    coin_5_decreased = pyqtSignal()
    coin_5_increased = pyqtSignal()

    def __init__(self, background_image_path=None):
        super().__init__()
        self.background_pixmap = None
        self.setup_ui()
        self._load_background_image(background_image_path)

    def _load_background_image(self, background_image_path=None):
        """
        Loads the background image for the admin panel.
        If no path is provided, tries to load the default admin panel background.
        """
        try:
            if background_image_path:
                self.set_background_image(background_image_path)
            else:
                # Get the directory of the current script (screens/admin/)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # Navigate up to the project root (SSP) and then into the assets folder
                image_path = os.path.join(current_dir, '..', '..', 'assets', 'admin_panel_screen background.png')
                # Normalize the path to resolve ".." and ensure OS compatibility
                normalized_path = os.path.normpath(image_path)
                self.set_background_image(normalized_path)
        except Exception as e:
            print(f"ERROR: Could not load admin panel background image. {e}")

    def set_background_image(self, image_path):
        """Sets the background image from the given path."""
        try:
            self.background_pixmap = QPixmap(image_path)
            if self.background_pixmap.isNull():
                print(f"ERROR: Failed to load background image from {image_path}")
                self.background_pixmap = None
            else:
                print(f"✅ Admin panel background image loaded: {image_path}")
        except Exception as e:
            print(f"ERROR: Could not set background image: {e}")
            self.background_pixmap = None

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.background_pixmap:
            painter.drawPixmap(self.rect(), self.background_pixmap)
        else:
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
        super().paintEvent(event)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 5, 20, 15)  # Reduced top margin
        layout.setSpacing(10)

        # Add empty space from top to push content down
        top_spacer = QLabel("")
        top_spacer.setFixedHeight(120)  # Increased space to push container further down
        layout.addWidget(top_spacer)

        content_frame = self._create_content_frame()
        
        back_button = QPushButton("← Back to Main Screen")
        back_button.setMinimumHeight(60)
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #ff0000; color: white; font-size: 16px; font-weight: bold;
                border: none; border-radius: 8px; padding: 8px;
            }
            QPushButton:hover { background-color: #ffb84d; }
        """)
        back_button.clicked.connect(self.back_clicked.emit)
        
        # Make back button smaller width
        back_button.setFixedWidth(200)  # Reduced width
        back_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout.addWidget(content_frame, 1)
        
        # Create a container for both buttons to be on the same horizontal level
        buttons_container = QWidget()
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(15, 10, 15, 0)  # Match content frame margins with top spacing
        
        # Add View Data Logs button to the right side
        view_logs_button = QPushButton("View Data Logs", clicked=self.view_data_logs_clicked.emit)
        view_logs_button.setFixedWidth(200)  # Match back button width
        view_logs_button.setFixedHeight(60)  # Match back button height
        view_logs_button.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="16px"))
        
        # Add both buttons to the same horizontal layout
        buttons_layout.addWidget(back_button)
        buttons_layout.addStretch()  # Push view logs button to the right
        buttons_layout.addWidget(view_logs_button)
        
        layout.addWidget(buttons_container)

    def _create_content_frame(self):
        frame = QFrame()
        frame.setObjectName("contentFrame")
        frame.setStyleSheet("""
            #contentFrame {
                background-color: transparent;
                border: none;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 5, 15, 10)  # Reduced bottom margin
        layout.setSpacing(8)  # Reduced spacing
        layout.addWidget(self._create_paper_management_group())
        layout.addWidget(self._create_coin_management_group())
        layout.addWidget(self._create_cmyk_management_group())
        return frame

    def _create_paper_management_group(self):
        group = QGroupBox("Paper Management")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Paper count with +/- buttons
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Paper Count:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;"))
        
        # Minus button
        self.paper_minus_btn = QPushButton("-")
        self.paper_minus_btn.setStyleSheet(self._get_copies_button_style())
        self.paper_minus_btn.clicked.connect(self.paper_decreased.emit)
        count_layout.addWidget(self.paper_minus_btn)
        
        # Count label
        self.paper_count_label = QLabel("0")
        self.paper_count_label.setStyleSheet(self._get_copies_label_style())
        count_layout.addWidget(self.paper_count_label)
        
        # Plus button
        self.paper_plus_btn = QPushButton("+")
        self.paper_plus_btn.setStyleSheet(self._get_copies_button_style())
        self.paper_plus_btn.clicked.connect(self.paper_increased.emit)
        count_layout.addWidget(self.paper_plus_btn)
        
        count_layout.addStretch()
        layout.addLayout(count_layout)

        # Reset button
        button_layout = QHBoxLayout()
        reset_paper_btn = QPushButton("Refill", clicked=self.reset_paper_clicked.emit)
        reset_paper_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        reset_paper_btn.setFixedHeight(45)
        
        button_layout.addStretch()
        button_layout.addWidget(reset_paper_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group

    def _create_coin_management_group(self):
        group = QGroupBox("Coin Inventory")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # P1 Coins with +/- buttons
        p1_layout = QHBoxLayout()
        p1_layout.addWidget(QLabel("P1 Coins:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;"))
        
        # P1 Minus button
        self.coin_1_minus_btn = QPushButton("-")
        self.coin_1_minus_btn.setStyleSheet(self._get_copies_button_style())
        self.coin_1_minus_btn.clicked.connect(self.coin_1_decreased.emit)
        p1_layout.addWidget(self.coin_1_minus_btn)
        
        # P1 Count label
        self.coin_1_label = QLabel("0")
        self.coin_1_label.setStyleSheet(self._get_copies_label_style())
        p1_layout.addWidget(self.coin_1_label)
        
        # P1 Plus button
        self.coin_1_plus_btn = QPushButton("+")
        self.coin_1_plus_btn.setStyleSheet(self._get_copies_button_style())
        self.coin_1_plus_btn.clicked.connect(self.coin_1_increased.emit)
        p1_layout.addWidget(self.coin_1_plus_btn)
        
        p1_layout.addStretch()
        layout.addLayout(p1_layout)

        # P5 Coins with +/- buttons
        p5_layout = QHBoxLayout()
        p5_layout.addWidget(QLabel("P5 Coins:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;"))
        
        # P5 Minus button
        self.coin_5_minus_btn = QPushButton("-")
        self.coin_5_minus_btn.setStyleSheet(self._get_copies_button_style())
        self.coin_5_minus_btn.clicked.connect(self.coin_5_decreased.emit)
        p5_layout.addWidget(self.coin_5_minus_btn)
        
        # P5 Count label
        self.coin_5_label = QLabel("0")
        self.coin_5_label.setStyleSheet(self._get_copies_label_style())
        p5_layout.addWidget(self.coin_5_label)
        
        # P5 Plus button
        self.coin_5_plus_btn = QPushButton("+")
        self.coin_5_plus_btn.setStyleSheet(self._get_copies_button_style())
        self.coin_5_plus_btn.clicked.connect(self.coin_5_increased.emit)
        p5_layout.addWidget(self.coin_5_plus_btn)
        
        p5_layout.addStretch()
        layout.addLayout(p5_layout)

        # Reset button
        button_layout = QHBoxLayout()
        reset_coins_btn = QPushButton("Refill All", clicked=self.reset_coins_clicked.emit)
        reset_coins_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        reset_coins_btn.setFixedHeight(45)
        
        button_layout.addStretch()
        button_layout.addWidget(reset_coins_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group

    def _create_cmyk_management_group(self):
        group = QGroupBox("CMYK Ink Levels")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # Create horizontal layouts for each CMYK pair with values immediately next to labels
        # Cyan and Magenta row
        cm_row = QHBoxLayout()
        cm_row.setSpacing(10)
        
        # Cyan Level
        cyan_layout = QHBoxLayout()
        cyan_label = QLabel("Cyan:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;")
        cyan_label.setFixedWidth(90)
        cyan_layout.addWidget(cyan_label)
        
        self.cyan_input = QLineEdit()
        self.cyan_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.cyan_input.setAlignment(Qt.AlignLeft)
        self.cyan_input.setFixedWidth(100)
        self.cyan_input.setFixedHeight(35)
        self.cyan_input.setStyleSheet("""
            QLineEdit {
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 6px;
                padding: 5px 10px;
            }
            QLineEdit:focus { border: 4px solid #2a5d1a; }
        """)
        cyan_layout.addWidget(self.cyan_input)
        cyan_layout.addStretch()
        
        # Magenta Level
        magenta_layout = QHBoxLayout()
        magenta_label = QLabel("Magenta:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;")
        magenta_label.setFixedWidth(90)
        magenta_layout.addWidget(magenta_label)
        
        self.magenta_input = QLineEdit()
        self.magenta_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.magenta_input.setAlignment(Qt.AlignLeft)
        self.magenta_input.setFixedWidth(100)
        self.magenta_input.setFixedHeight(35)
        self.magenta_input.setStyleSheet("""
            QLineEdit {
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 6px;
                padding: 5px 10px;
            }
            QLineEdit:focus { border: 4px solid #2a5d1a; }
        """)
        magenta_layout.addWidget(self.magenta_input)
        magenta_layout.addStretch()
        
        cm_row.addLayout(cyan_layout)
        cm_row.addLayout(magenta_layout)
        layout.addLayout(cm_row)

        # Yellow and Black row
        yk_row = QHBoxLayout()
        yk_row.setSpacing(10)
        
        # Yellow Level
        yellow_layout = QHBoxLayout()
        yellow_label = QLabel("Yellow:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;")
        yellow_label.setFixedWidth(90)
        yellow_layout.addWidget(yellow_label)
        
        self.yellow_input = QLineEdit()
        self.yellow_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.yellow_input.setAlignment(Qt.AlignLeft)
        self.yellow_input.setFixedWidth(100)
        self.yellow_input.setFixedHeight(35)
        self.yellow_input.setStyleSheet("""
            QLineEdit {
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 6px;
                padding: 5px 10px;
            }
            QLineEdit:focus { border: 4px solid #2a5d1a; }
        """)
        yellow_layout.addWidget(self.yellow_input)
        yellow_layout.addStretch()
        
        # Black Level
        black_layout = QHBoxLayout()
        black_label = QLabel("Black:", styleSheet="color: #36454F; font-size: 18px; font-weight: bold;")
        black_label.setFixedWidth(90)
        black_layout.addWidget(black_label)
        
        self.black_input = QLineEdit()
        self.black_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.black_input.setAlignment(Qt.AlignLeft)
        self.black_input.setFixedWidth(100)
        self.black_input.setFixedHeight(35)
        self.black_input.setStyleSheet("""
            QLineEdit {
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 6px;
                padding: 5px 10px;
            }
            QLineEdit:focus { border: 4px solid #2a5d1a; }
        """)
        black_layout.addWidget(self.black_input)
        black_layout.addStretch()
        
        yk_row.addLayout(yellow_layout)
        yk_row.addLayout(black_layout)
        layout.addLayout(yk_row)

        # Buttons - more compact
        button_layout = QHBoxLayout()
        update_cmyk_btn = QPushButton("Update", 
                                    clicked=lambda: self._update_cmyk_levels())
        update_cmyk_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        update_cmyk_btn.setFixedHeight(45)
        
        reset_cmyk_btn = QPushButton("Refill All", 
                                   clicked=self.reset_cmyk_clicked.emit)
        reset_cmyk_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        reset_cmyk_btn.setFixedHeight(45)
        
        refresh_cmyk_btn = QPushButton("Refresh", 
                                     clicked=self.refresh_cmyk_clicked.emit)
        refresh_cmyk_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        refresh_cmyk_btn.setFixedHeight(45)
        
        button_layout.addStretch()
        button_layout.addWidget(update_cmyk_btn)
        button_layout.addWidget(reset_cmyk_btn)
        button_layout.addWidget(refresh_cmyk_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group


    def update_paper_count_display(self, count: int, color: str):
        """Updates the paper count input field and its style."""
        self.paper_count_input.setText(str(count))
        self.paper_count_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)

    def update_coin_count_display(self, coin_1_count: int, coin_5_count: int):
        """Updates the coin count input fields."""
        self.coin_1_input.setText(str(coin_1_count))
        self.coin_5_input.setText(str(coin_5_count))
        
        # Set styling based on coin levels
        coin_1_color = self._get_coin_color(coin_1_count)
        coin_5_color = self._get_coin_color(coin_5_count)
        
        self.coin_1_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)
        
        self.coin_5_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)

    def _get_coin_color(self, count: int) -> str:
        """Determines the display color based on the coin count."""
        if count <= 20: return "#dc3545"  # Red - Low
        if count <= 50: return "#ffc107"  # Yellow - Medium
        return "#28a745"  # Green - Good

    def _update_cmyk_levels(self):
        """Helper method to update CMYK levels from input fields."""
        try:
            cyan = float(self.cyan_input.text()) if self.cyan_input.text() else 0.0
            magenta = float(self.magenta_input.text()) if self.magenta_input.text() else 0.0
            yellow = float(self.yellow_input.text()) if self.yellow_input.text() else 0.0
            black = float(self.black_input.text()) if self.black_input.text() else 0.0
            
            # Validate ranges
            if not (0.0 <= cyan <= 100.0 and 0.0 <= magenta <= 100.0 and 
                    0.0 <= yellow <= 100.0 and 0.0 <= black <= 100.0):
                self.show_message_box("Invalid Input", "CMYK values must be between 0.0 and 100.0")
                return
                
            self.update_cmyk_clicked.emit(cyan, magenta, yellow, black)
        except ValueError:
            self.show_message_box("Invalid Input", "Please enter valid decimal numbers for CMYK levels")

    def update_cmyk_display(self, cyan: float, magenta: float, yellow: float, black: float):
        """Updates the CMYK input fields with current values."""
        self.cyan_input.setText(f"{cyan:.1f}")
        self.magenta_input.setText(f"{magenta:.1f}")
        self.yellow_input.setText(f"{yellow:.1f}")
        self.black_input.setText(f"{black:.1f}")
        
        # Update styling based on ink levels
        self._update_cmyk_styling(cyan, magenta, yellow, black)

    def _update_cmyk_styling(self, cyan: float, magenta: float, yellow: float, black: float):
        """Updates the styling of CMYK input fields based on ink levels."""
        cyan_color = self._get_ink_color(cyan)
        magenta_color = self._get_ink_color(magenta)
        yellow_color = self._get_ink_color(yellow)
        black_color = self._get_ink_color(black)
        
        self.cyan_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)
        
        self.magenta_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)
        
        self.yellow_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)
        
        self.black_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: white; color: #36454F; font-size: 22px;
                font-weight: bold; border: 4px solid #1e440a; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 4px solid #2a5d1a; }}
        """)

    def _get_ink_color(self, level: float) -> str:
        """Determines the display color based on the ink level."""
        if level <= 10.0: return "#dc3545"  # Red - Low
        if level <= 25.0: return "#ffc107"  # Yellow - Medium
        return "#28a745"  # Green - Good


    def show_message_box(self, title: str, text: str):
        QMessageBox.warning(self, title, text)

    def _get_groupbox_style(self):
        return """
            QGroupBox {
                color: #36454F;
                font-size: 18px;
                font-weight: bold;
                border: 4px solid #1e440a;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: rgba(255, 255, 255, 0.9);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """

    def _get_button_style(self, bg_color, hover_color, font_size="16px"):
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                padding: 8px 15px;
                border-radius: 5px;
                font-size: {font_size};
                font-weight: bold;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """
    
    def _get_copies_button_style(self):
        return """
            QPushButton {
                background-color: #1e440a;
                color: white;
                border-radius: 4px;
                font-size: 22px;
                width: 44px;
                height: 44px;
                min-width: 44px;
                max-width: 44px;
                min-height: 44px;
                max-height: 44px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #2a5d1a;
            }
        """
    
    def _get_copies_label_style(self):
        return """
            QLabel {
                background-color: transparent;
                color: #36454F;
                font-size: 22px;
                min-width: 40px;
                max-width: 40px;
                border: none;
                font-weight: bold;
                qproperty-alignment: AlignCenter;
            }
        """
    
    def update_paper_count_display(self, count, color=None):
        """Updates the paper count display."""
        self.paper_count_label.setText(str(count))
        # Use consistent text color like other labels
        self.paper_count_label.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                color: #36454F;
                font-size: 22px;
                min-width: 40px;
                max-width: 40px;
                border: none;
                font-weight: bold;
                qproperty-alignment: AlignCenter;
            }}
        """)
    
    def update_coin_count_display(self, p1_count, p5_count):
        """Updates the coin count displays."""
        self.coin_1_label.setText(str(p1_count))
        self.coin_5_label.setText(str(p5_count))