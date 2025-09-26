# screens/admin/view.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QLineEdit, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator, QPixmap, QPainter

class AdminScreenView(QWidget):
    """The user interface for the Admin Panel. Contains no logic."""
    back_clicked = pyqtSignal()
    view_data_logs_clicked = pyqtSignal()
    update_paper_clicked = pyqtSignal(str)
    reset_paper_clicked = pyqtSignal()
    update_coin_1_clicked = pyqtSignal(str)
    update_coin_5_clicked = pyqtSignal(str)
    reset_coins_clicked = pyqtSignal()

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
        layout.setContentsMargins(50, 30, 50, 30)
        layout.setSpacing(20)

        title = QLabel("Admin Panel")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-size: 48px; font-weight: bold; text-shadow: 2px 2px 4px #000000;")

        content_frame = self._create_content_frame()
        
        back_button = QPushButton("← Back to Main Screen")
        back_button.setMinimumHeight(60)
        back_button.setCursor(Qt.PointingHandCursor)
        back_button.setStyleSheet("""
            QPushButton {
                background-color: #c83c3c; color: white; font-size: 20px; font-weight: bold;
                border: 1px solid #d85050; border-radius: 10px; padding: 10px;
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
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)
        layout.addWidget(self._create_paper_management_group())
        layout.addWidget(self._create_coin_management_group())
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
        self.coin_1_input.setFixedWidth(100)
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
        self.coin_5_input.setFixedWidth(100)
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
        ink_layout.addWidget(QLabel("Monitoring Not Implemented", styleSheet="color: #999999; font-size: 18px; font-style: italic;"))
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
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {coin_1_color}; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)
        
        self.coin_5_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #1f1f38; color: white; font-size: 18px;
                font-weight: bold; border: 3px solid {coin_5_color}; border-radius: 8px;
                padding: 5px 10px;
            }}
            QLineEdit:focus {{ border: 3px solid #ff9800; }}
        """)

    def _get_coin_color(self, count: int) -> str:
        """Determines the display color based on the coin count."""
        if count <= 20: return "#dc3545"  # Red - Low
        if count <= 50: return "#ffc107"  # Yellow - Medium
        return "#28a745"  # Green - Good

    def show_message_box(self, title: str, text: str):
        QMessageBox.warning(self, title, text)

    def _get_groupbox_style(self):
        return """ ... """ # Style string from original file

    def _get_button_style(self, bg_color, hover_color, font_size="16px"):
        return f""" ... """ # Style string from original file