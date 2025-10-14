# screens/data_viewer/view.py

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, 
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter

class DataViewerScreenView(QWidget):
    """The user interface for the Data Viewer Screen. Contains no logic."""
    back_clicked = pyqtSignal()
    refresh_transactions_clicked = pyqtSignal()
    refresh_cash_inventory_clicked = pyqtSignal()
    refresh_error_log_clicked = pyqtSignal()
    
    def __init__(self, background_image_path=None):
        super().__init__()
        self.background_pixmap = None
        self.setup_ui()
        self._load_background_image(background_image_path)

    def _load_background_image(self, background_image_path=None):
        """
        Loads the background image for the data viewer screen.
        If no path is provided, tries to load the default data viewer background.
        """
        try:
            if background_image_path:
                self.set_background_image(background_image_path)
            else:
                # Get the directory of the current script (screens/data_viewer/)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # Navigate up to the project root (SSP) and then into the assets folder
                image_path = os.path.join(current_dir, '..', '..', 'assets', 'data_viewer_screen background.png')
                # Normalize the path to resolve ".." and ensure OS compatibility
                normalized_path = os.path.normpath(image_path)
                self.set_background_image(normalized_path)
        except Exception as e:
            print(f"ERROR: Could not load data viewer background image. {e}")

    def set_background_image(self, image_path):
        """Sets the background image from the given path."""
        try:
            self.background_pixmap = QPixmap(image_path)
            if self.background_pixmap.isNull():
                print(f"ERROR: Failed to load background image from {image_path}")
                self.background_pixmap = None
            else:
                print(f"✅ Data viewer background image loaded: {image_path}")
        except Exception as e:
            print(f"ERROR: Could not set background image: {e}")
            self.background_pixmap = None

    def paintEvent(self, event):
        """Custom paint event to draw background image."""
        painter = QPainter(self)
        if self.background_pixmap:
            painter.drawPixmap(self.rect(), self.background_pixmap)
        else:
            # Fallback to a dark background if the image fails to load
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
        super().paintEvent(event)
    
    def setup_ui(self):
        """Sets up the user interface components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 5, 20, 15)
        layout.setSpacing(10)

        # Add empty space from top to push content down
        top_spacer = QLabel("")
        top_spacer.setFixedHeight(50)
        layout.addWidget(top_spacer)

        # --- Content Container ---
        content_frame = self._create_content_frame()
        
        # --- Buttons Container ---
        buttons_container = QWidget()
        buttons_layout = QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(15, 10, 15, 0)
        
        # Back Button
        self.back_button = QPushButton("← Back to Admin Screen")
        self.back_button.setFixedWidth(260)
        self.back_button.setFixedHeight(48)
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.setStyleSheet(self.get_back_button_style())
        self.back_button.clicked.connect(self.back_clicked.emit)
        
        # Refresh Data Button
        self.refresh_data_button = QPushButton("Refresh Data")
        self.refresh_data_button.setFixedWidth(200)
        self.refresh_data_button.setFixedHeight(48)
        self.refresh_data_button.setStyleSheet(self.get_refresh_button_style())
        self.refresh_data_button.clicked.connect(self._on_refresh_clicked)
        
        buttons_layout.addWidget(self.back_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.refresh_data_button)
        
        layout.addWidget(content_frame, 1)
        layout.addWidget(buttons_container)
        self.setLayout(layout)
    
    def _create_content_frame(self):
        """Creates the content frame with tab widget."""
        frame = QWidget()
        frame.setObjectName("contentFrame")
        frame.setStyleSheet("""
            #contentFrame {
                background-color: transparent;
                border: 2px solid #1e440a;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 5, 15, 10)
        layout.setSpacing(8)
        
        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(self.get_tab_widget_style())
        
        # Add tabs for different data views
        self.tab_widget.addTab(self.create_transactions_tab(), "Transactions")
        self.tab_widget.addTab(self.create_cash_inventory_tab(), "Cash Inventory")
        self.tab_widget.addTab(self.create_error_log_tab(), "Error Log")
        
        layout.addWidget(self.tab_widget)
        return frame
    
    def _on_refresh_clicked(self):
        """Handle refresh button click based on current tab."""
        current_index = self.tab_widget.currentIndex()
        if current_index == 0:  # Transactions
            self.refresh_transactions_clicked.emit()
        elif current_index == 1:  # Cash Inventory
            self.refresh_cash_inventory_clicked.emit()
        elif current_index == 2:  # Error Log
            self.refresh_error_log_clicked.emit()
    
    def create_transactions_tab(self):
        """Creates the transactions tab."""
        self.transactions_table = QTableWidget()
        self.transactions_table.setStyleSheet(self.get_table_style())
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.transactions_table)
        
        return widget

    def create_cash_inventory_tab(self):
        """Creates the cash inventory tab."""
        self.cash_inventory_table = QTableWidget()
        self.cash_inventory_table.setStyleSheet(self.get_table_style())
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.cash_inventory_table)
        
        return widget
        
    def create_error_log_tab(self):
        """Creates the error log tab."""
        self.error_log_table = QTableWidget()
        self.error_log_table.setStyleSheet(self.get_table_style())
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.error_log_table)
        
        return widget
    
    def update_transactions_table(self, transactions):
        """Updates the transactions table with new data."""
        self.transactions_table.clear()
        self.transactions_table.setColumnCount(9)
        self.transactions_table.setHorizontalHeaderLabels([
            "ID", "Date/Time", "File Name", "Pages", "Copies",
            "Color Mode", "Total Cost", "Amount Paid", "Status"
        ])
        self.transactions_table.setRowCount(len(transactions))
        
        for i, trans in enumerate(transactions):
            self.transactions_table.setItem(i, 0, QTableWidgetItem(str(trans['id'])))
            self.transactions_table.setItem(i, 1, QTableWidgetItem(str(trans['timestamp'])))
            self.transactions_table.setItem(i, 2, QTableWidgetItem(trans['file_name']))
            self.transactions_table.setItem(i, 3, QTableWidgetItem(str(trans['pages'])))
            self.transactions_table.setItem(i, 4, QTableWidgetItem(str(trans['copies'])))
            self.transactions_table.setItem(i, 5, QTableWidgetItem(trans['color_mode']))
            self.transactions_table.setItem(i, 6, QTableWidgetItem(f"₱{trans['total_cost']:.2f}"))
            self.transactions_table.setItem(i, 7, QTableWidgetItem(f"₱{trans['amount_paid']:.2f}"))
            self.transactions_table.setItem(i, 8, QTableWidgetItem(trans['status']))
        
        # Make columns evenly distributed across the entire width
        header = self.transactions_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(9):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
    
    def update_cash_inventory_table(self, inventory):
        """Updates the cash inventory table with new data."""
        self.cash_inventory_table.clear()
        self.cash_inventory_table.setColumnCount(4)
        self.cash_inventory_table.setHorizontalHeaderLabels(["Denomination", "Count", "Type", "Last Updated"])
        self.cash_inventory_table.setRowCount(len(inventory))
        
        for i, item in enumerate(inventory):
            self.cash_inventory_table.setItem(i, 0, QTableWidgetItem(f"₱{item['denomination']}"))
            self.cash_inventory_table.setItem(i, 1, QTableWidgetItem(str(item['count'])))
            self.cash_inventory_table.setItem(i, 2, QTableWidgetItem(item['type']))
            self.cash_inventory_table.setItem(i, 3, QTableWidgetItem(str(item['last_updated'])))
        
        # Make columns evenly distributed across the entire width
        header = self.cash_inventory_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
    
    def update_error_log_table(self, errors):
        """Updates the error log table with new data."""
        self.error_log_table.clear()
        self.error_log_table.setColumnCount(4)
        self.error_log_table.setHorizontalHeaderLabels(["Date/Time", "Error Type", "Message", "Context"])
        self.error_log_table.setRowCount(len(errors))
        
        for i, error in enumerate(errors):
            self.error_log_table.setItem(i, 0, QTableWidgetItem(str(error['timestamp'])))
            self.error_log_table.setItem(i, 1, QTableWidgetItem(error['error_type']))
            self.error_log_table.setItem(i, 2, QTableWidgetItem(error['message']))
            self.error_log_table.setItem(i, 3, QTableWidgetItem(error['context']))
        
        # Make columns evenly distributed across the entire width
        header = self.error_log_table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
    
    def get_tab_widget_style(self):
        """Returns the style for the tab widget."""
        return """
            QTabWidget::pane { 
                border: 1px solid #2a5d1a; 
            }
            QTabBar::tab {
                background-color: #15300a;
                color: white;
                padding: 10px 20px;
                margin: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border: 1px solid #2a5d1a;
                border-bottom: none;
                font-size: 16px;
                font-weight: bold;
                min-height: 18px;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                background-color: #1e440a;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #1e440a;
                color: white;
            }
        """

    def get_table_style(self):
        """Returns the style for tables."""
        return """
            QTableWidget { 
                background-color: white;
                color: #36454F;
                gridline-color: #d3d3d3;
                border: none; 
            }
            QHeaderView::section { 
                background-color: #1e440a;
                color: white; 
                padding: 5px; 
                border: 1px solid #2a5d1a; 
            }
            QTableWidget::item { 
                border-bottom: 1px solid #dcdcdc;
                padding: 5px; 
            }
        """

    def get_button_style(self):
        """Returns the style for buttons."""
        return """
            QPushButton { 
                background-color: #1e440a; /* Green theme button */
                color: white; 
                padding: 8px 15px; 
                border-radius: 5px; 
                font-size: 14px; 
                border: none; 
            }
            QPushButton:hover { 
                background-color: #2a5d1a; /* Lighter green on hover */
            }
        """

    def get_back_button_style(self):
        """Returns the style for the back button."""
        return """
            QPushButton {
                background-color: #ff0000;
                color: white; font-size: 16px; font-weight: bold;
                border: none; border-radius: 8px; padding: 8px;
            }
            QPushButton:hover { background-color: #ffb84d; }
        """
    
    def get_refresh_button_style(self):
        """Returns the style for the refresh button."""
        return """
            QPushButton {
                background-color: #1e440a; color: white; font-size: 16px; font-weight: bold;
                border: none; border-radius: 8px; padding: 8px;
            }
            QPushButton:hover { background-color: #2a5d1a; }
        """
