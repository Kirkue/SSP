# screens/dialogs/payment_suggestion_dialog/view.py

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPalette


class PaymentSuggestionDialog(QDialog):
    """Dialog to show payment suggestions based on available change."""
    
    suggestion_selected = pyqtSignal(float)  # Emitted when user selects a suggestion
    exact_payment_requested = pyqtSignal()   # Emitted when user wants exact payment
    
    def __init__(self, total_cost, suggestions, status_message, parent=None):
        super().__init__(parent)
        self.total_cost = total_cost
        self.suggestions = suggestions
        self.status_message = status_message
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Payment Options")
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("Payment Options")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Total cost display
        cost_label = QLabel(f"Total Cost: ₱{self.total_cost:.2f}")
        cost_font = QFont()
        cost_font.setPointSize(14)
        cost_font.setBold(True)
        cost_label.setFont(cost_font)
        cost_label.setAlignment(Qt.AlignCenter)
        cost_label.setStyleSheet("color: #2c3e50; background-color: #ecf0f1; padding: 10px; border-radius: 5px;")
        main_layout.addWidget(cost_label)
        
        # Status message
        status_label = QLabel(self.status_message)
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setWordWrap(True)
        status_label.setStyleSheet("color: #e74c3c; font-weight: bold; padding: 8px;")
        main_layout.addWidget(status_label)
        
        # Suggestions scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(200)
        
        suggestions_widget = QWidget()
        suggestions_layout = QVBoxLayout(suggestions_widget)
        suggestions_layout.setSpacing(8)
        
        # Add suggestion buttons
        for i, suggestion in enumerate(self.suggestions[:5]):  # Show max 5 suggestions
            suggestion_button = self.create_suggestion_button(suggestion, i)
            suggestions_layout.addWidget(suggestion_button)
        
        scroll_area.setWidget(suggestions_widget)
        main_layout.addWidget(scroll_area)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        # Exact payment button
        exact_button = QPushButton("Pay Exact Amount")
        exact_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        exact_button.clicked.connect(self.exact_payment_requested.emit)
        button_layout.addWidget(exact_button)
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
    def create_suggestion_button(self, suggestion, index):
        """Create a suggestion button."""
        button = QPushButton()
        button.setFixedHeight(50)
        
        amount = suggestion['amount']
        change = suggestion['change']
        reason = suggestion['reason']
        priority = suggestion['priority']
        
        # Set button text
        if change == 0:
            button_text = f"₱{amount:.2f} - Exact Payment"
        else:
            button_text = f"₱{amount:.2f} (₱{change:.2f} change) - {reason}"
        
        button.setText(button_text)
        
        # Set button style based on priority
        if priority == 'highest':
            button.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: 2px solid #2980b9;
                    border-radius: 5px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
        elif priority == 'high':
            button.setStyleSheet("""
                QPushButton {
                    background-color: #9b59b6;
                    color: white;
                    border: 2px solid #8e44ad;
                    border-radius: 5px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
                QPushButton:hover {
                    background-color: #8e44ad;
                }
            """)
        else:
            button.setStyleSheet("""
                QPushButton {
                    background-color: #34495e;
                    color: white;
                    border: 2px solid #2c3e50;
                    border-radius: 5px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 15px;
                }
                QPushButton:hover {
                    background-color: #2c3e50;
                }
            """)
        
        # Connect click event
        button.clicked.connect(lambda: self.suggestion_selected.emit(amount))
        
        return button
