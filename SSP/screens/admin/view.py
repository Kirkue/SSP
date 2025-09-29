# screens/admin/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QLineEdit, QMessageBox, QGroupBox
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

    def __init__(self, background_image_path=None):
        super().__init__()
        self.background_pixmap = QPixmap(background_image_path) if background_image_path else None
        self.setup_ui()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.background_pixmap:
            painter.drawPixmap(self.rect(), self.background_pixmap)
        else:
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
        super().paintEvent(event)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        title = QLabel("Admin Panel")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-size: 32px; font-weight: bold; text-shadow: 2px 2px 4px #000000;")

        content_frame = self._create_content_frame()
        
        back_button = QPushButton("← Back to Main Screen")
        back_button.setMinimumHeight(40)
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #c83c3c; color: white; font-size: 16px; font-weight: bold;
                border: 1px solid #d85050; border-radius: 8px; padding: 8px;
            }
            QPushButton:hover { background-color: #e05a5a; }
        """)
        back_button.clicked.connect(self.back_clicked.emit)

        layout.addWidget(title)
        layout.addWidget(content_frame, 1)
        layout.addWidget(back_button)

    def _create_content_frame(self):
        frame = QFrame()
        frame.setObjectName("contentFrame")
        frame.setStyleSheet("""
            #contentFrame {
                background-color: rgba(15, 31, 0, 0.85);
                border: 1px solid rgba(42, 93, 26, 0.9);
                border-radius: 20px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        layout.addWidget(self._create_paper_management_group())
        layout.addWidget(self._create_coin_management_group())
        layout.addWidget(self._create_cmyk_management_group())
        layout.addWidget(self._create_system_data_group())
        return frame

    def _create_paper_management_group(self):
        group = QGroupBox("Paper Management")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(15)

        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Current Paper Count:", styleSheet="color: #e0e0e0; font-size: 18px;"))
        count_layout.addStretch()
        
        self.paper_count_input = QLineEdit()
        self.paper_count_input.setValidator(QIntValidator(0, 100))
        self.paper_count_input.setAlignment(Qt.AlignCenter)
        self.paper_count_input.setFixedWidth(100)
        self.paper_count_input.returnPressed.connect(
            lambda: self.update_paper_clicked.emit(self.paper_count_input.text())
        )
        count_layout.addWidget(self.paper_count_input)
        layout.addLayout(count_layout)

        button_layout = QHBoxLayout()
        update_paper_btn = QPushButton("Update Count", clicked=lambda: self.update_paper_clicked.emit(self.paper_count_input.text()))
        update_paper_btn.setStyleSheet(self._get_button_style("#ff9800", "#f57c00"))
        
        reset_paper_btn = QPushButton("Refill (Reset to 100)", clicked=self.reset_paper_clicked.emit)
        reset_paper_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a"))
        
        button_layout.addStretch()
        button_layout.addWidget(update_paper_btn)
        button_layout.addWidget(reset_paper_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group

    def _create_coin_management_group(self):
        group = QGroupBox("Coin Inventory Management")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(15)

        # 1 Peso Coins Section
        peso_1_layout = QHBoxLayout()
        peso_1_layout.addWidget(QLabel("₱1 Coins:", styleSheet="color: #e0e0e0; font-size: 18px; font-weight: bold;"))
        peso_1_layout.addStretch()
        
        self.coin_1_input = QLineEdit()
        self.coin_1_input.setValidator(QIntValidator(0, 1000))
        self.coin_1_input.setAlignment(Qt.AlignCenter)
        self.coin_1_input.setFixedWidth(150)
        self.coin_1_input.setFixedHeight(40)
        self.coin_1_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 24px;
                font-weight: bold; border: 3px solid #28a745; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        self.coin_1_input.returnPressed.connect(
            lambda: self.update_coin_1_clicked.emit(self.coin_1_input.text())
        )
        peso_1_layout.addWidget(self.coin_1_input)
        layout.addLayout(peso_1_layout)

        # 5 Peso Coins Section
        peso_5_layout = QHBoxLayout()
        peso_5_layout.addWidget(QLabel("₱5 Coins:", styleSheet="color: #e0e0e0; font-size: 18px; font-weight: bold;"))
        peso_5_layout.addStretch()
        
        self.coin_5_input = QLineEdit()
        self.coin_5_input.setValidator(QIntValidator(0, 1000))
        self.coin_5_input.setAlignment(Qt.AlignCenter)
        self.coin_5_input.setFixedWidth(150)
        self.coin_5_input.setFixedHeight(40)
        self.coin_5_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 24px;
                font-weight: bold; border: 3px solid #28a745; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        self.coin_5_input.returnPressed.connect(
            lambda: self.update_coin_5_clicked.emit(self.coin_5_input.text())
        )
        peso_5_layout.addWidget(self.coin_5_input)
        layout.addLayout(peso_5_layout)

        # Buttons
        button_layout = QHBoxLayout()
        update_coin_1_btn = QPushButton("Update ₱1", clicked=lambda: self.update_coin_1_clicked.emit(self.coin_1_input.text()))
        update_coin_1_btn.setStyleSheet(self._get_button_style("#ff9800", "#f57c00"))
        
        update_coin_5_btn = QPushButton("Update ₱5", clicked=lambda: self.update_coin_5_clicked.emit(self.coin_5_input.text()))
        update_coin_5_btn.setStyleSheet(self._get_button_style("#ff9800", "#f57c00"))
        
        reset_coins_btn = QPushButton("Refill All Coins", clicked=self.reset_coins_clicked.emit)
        reset_coins_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a"))
        
        button_layout.addStretch()
        button_layout.addWidget(update_coin_1_btn)
        button_layout.addWidget(update_coin_5_btn)
        button_layout.addWidget(reset_coins_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group

    def _create_cmyk_management_group(self):
        group = QGroupBox("CMYK Ink Level Management")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(15)

        # Cyan Level
        cyan_layout = QHBoxLayout()
        cyan_layout.addWidget(QLabel("Cyan (%):", styleSheet="color: #00bcd4; font-size: 18px; font-weight: bold;"))
        cyan_layout.addStretch()
        
        self.cyan_input = QLineEdit()
        self.cyan_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.cyan_input.setAlignment(Qt.AlignCenter)
        self.cyan_input.setFixedWidth(120)
        self.cyan_input.setFixedHeight(40)
        self.cyan_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid #00bcd4; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        cyan_layout.addWidget(self.cyan_input)
        layout.addLayout(cyan_layout)

        # Magenta Level
        magenta_layout = QHBoxLayout()
        magenta_layout.addWidget(QLabel("Magenta (%):", styleSheet="color: #e91e63; font-size: 18px; font-weight: bold;"))
        magenta_layout.addStretch()
        
        self.magenta_input = QLineEdit()
        self.magenta_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.magenta_input.setAlignment(Qt.AlignCenter)
        self.magenta_input.setFixedWidth(120)
        self.magenta_input.setFixedHeight(40)
        self.magenta_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid #e91e63; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        magenta_layout.addWidget(self.magenta_input)
        layout.addLayout(magenta_layout)

        # Yellow Level
        yellow_layout = QHBoxLayout()
        yellow_layout.addWidget(QLabel("Yellow (%):", styleSheet="color: #ffeb3b; font-size: 18px; font-weight: bold;"))
        yellow_layout.addStretch()
        
        self.yellow_input = QLineEdit()
        self.yellow_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.yellow_input.setAlignment(Qt.AlignCenter)
        self.yellow_input.setFixedWidth(120)
        self.yellow_input.setFixedHeight(40)
        self.yellow_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid #ffeb3b; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        yellow_layout.addWidget(self.yellow_input)
        layout.addLayout(yellow_layout)

        # Black Level
        black_layout = QHBoxLayout()
        black_layout.addWidget(QLabel("Black (%):", styleSheet="color: #424242; font-size: 18px; font-weight: bold;"))
        black_layout.addStretch()
        
        self.black_input = QLineEdit()
        self.black_input.setValidator(QDoubleValidator(0.0, 100.0, 2))
        self.black_input.setAlignment(Qt.AlignCenter)
        self.black_input.setFixedWidth(120)
        self.black_input.setFixedHeight(40)
        self.black_input.setStyleSheet("""
            QLineEdit {
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid #424242; border-radius: 8px;
                padding: 8px 12px;
            }
            QLineEdit:focus { border: 3px solid #ff9800; }
        """)
        black_layout.addWidget(self.black_input)
        layout.addLayout(black_layout)

        # Buttons
        button_layout = QHBoxLayout()
        update_cmyk_btn = QPushButton("Update CMYK Levels", 
                                    clicked=lambda: self._update_cmyk_levels())
        update_cmyk_btn.setStyleSheet(self._get_button_style("#ff9800", "#f57c00"))
        
        reset_cmyk_btn = QPushButton("Refill All Ink (100%)", 
                                   clicked=self.reset_cmyk_clicked.emit)
        reset_cmyk_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a"))
        
        button_layout.addStretch()
        button_layout.addWidget(update_cmyk_btn)
        button_layout.addWidget(reset_cmyk_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        return group

    def _create_system_data_group(self):
        group = QGroupBox("System & Data")
        group.setStyleSheet(self._get_groupbox_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(15)

        transaction_btn = QPushButton("View System Data Logs", clicked=self.view_data_logs_clicked.emit)
        transaction_btn.setMinimumHeight(50)
        transaction_btn.setStyleSheet(self._get_button_style("#1e440a", "#2a5d1a", font_size="18px"))
        layout.addWidget(transaction_btn)

        ink_layout = QHBoxLayout()
        ink_layout.addWidget(QLabel("Ink Level Status:", styleSheet="color: #e0e0e0; font-size: 18px;"))
        ink_layout.addStretch()
        self.ink_status_label = QLabel("Loading...", styleSheet="color: #999999; font-size: 18px; font-style: italic;")
        ink_layout.addWidget(self.ink_status_label)
        layout.addLayout(ink_layout)
        
        return group

    def update_paper_count_display(self, count: int, color: str):
        """Updates the paper count input field and its style."""
        self.paper_count_input.setText(str(count))
        self.paper_count_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {color}; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
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
                background-color: #1f1f38; color: white; font-size: 24px;
                font-weight: bold; border: 3px solid {coin_1_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)
        
        self.coin_5_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 24px;
                font-weight: bold; border: 3px solid {coin_5_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
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
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {cyan_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)
        
        self.magenta_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {magenta_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)
        
        self.yellow_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {yellow_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)
        
        self.black_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {black_color}; border-radius: 8px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)

    def _get_ink_color(self, level: float) -> str:
        """Determines the display color based on the ink level."""
        if level <= 10.0: return "#dc3545"  # Red - Low
        if level <= 25.0: return "#ffc107"  # Yellow - Medium
        return "#28a745"  # Green - Good

    def update_ink_status_display(self, cmyk_levels):
        """Updates the ink status display in the system data group."""
        if cmyk_levels:
            status_text = f"C:{cmyk_levels['cyan']:.1f}% M:{cmyk_levels['magenta']:.1f}% Y:{cmyk_levels['yellow']:.1f}% K:{cmyk_levels['black']:.1f}%"
            self.ink_status_label.setText(status_text)
            self.ink_status_label.setStyleSheet("color: #28a745; font-size: 18px; font-weight: bold;")
        else:
            self.ink_status_label.setText("No ink level data available")
            self.ink_status_label.setStyleSheet("color: #999999; font-size: 18px; font-style: italic;")

    def show_message_box(self, title: str, text: str):
        QMessageBox.warning(self, title, text)

    def _get_groupbox_style(self):
        return """ ... """ # Style string from original file

    def _get_button_style(self, bg_color, hover_color, font_size="16px"):
        return f""" ... """ # Style string from original file