# screens/print_options/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout, QMessageBox

from .model import PrintOptionsModel
from .view import PrintOptionsScreenView

class PrintOptionsController(QWidget):
    """Manages the Print Options screen's logic and UI."""
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = PrintOptionsModel()
        self.view = PrintOptionsScreenView()
        
        # Set the view's layout as this controller's layout
        self.setLayout(self.view.main_layout)
        
        self._connect_signals()

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller ---
        self.view.back_button_clicked.connect(self._go_back)
        self.view.continue_button_clicked.connect(self._continue_to_payment)
        self.view.bw_mode_clicked.connect(self._set_bw_mode)
        self.view.color_mode_clicked.connect(self._set_color_mode)
        self.view.copies_decreased.connect(self._decrease_copies)
        self.view.copies_increased.connect(self._increase_copies)
        
        # --- Model -> View ---
        self.model.cost_updated.connect(self.view.update_cost_display)
        self.model.analysis_started.connect(self._on_analysis_started)
        self.model.analysis_completed.connect(self._on_analysis_completed)
        self.model.analysis_error.connect(self._on_analysis_error)
        self.model.show_message.connect(self._show_message)
    
    def _set_bw_mode(self):
        """Sets black and white mode."""
        self.model.set_color_mode("Black and White")
        self.view.set_bw_mode()
        self._check_paper_availability()
    
    def _set_color_mode(self):
        """Sets color mode."""
        self.model.set_color_mode("Color")
        self.view.set_color_mode()
        self._check_paper_availability()
    
    def _decrease_copies(self):
        """Decreases the number of copies."""
        self.model.change_copies(-1)
        self.view.update_copies_display(self.model.get_copies())
        self._check_paper_availability()
    
    def _increase_copies(self):
        """Increases the number of copies."""
        self.model.change_copies(1)
        self.view.update_copies_display(self.model.get_copies())
        self._check_paper_availability()
    
    def _on_analysis_started(self):
        """Handles when analysis starts."""
        self.view.set_continue_button_enabled(False)
        self.view.set_analysis_status(
            "Analyzing pages and calculating cost...",
            "This may take a moment for large documents..."
        )
    
    def _on_analysis_completed(self, results):
        """Handles when analysis is completed."""
        print("Analysis completed, enabling continue button and checking paper availability")
        self.view.set_continue_button_enabled(True)
        # Check paper availability after analysis is complete with a small delay
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._check_paper_availability)
    
    def _on_analysis_error(self, error_message):
        """Handles analysis errors."""
        self.view.set_analysis_status("Error during analysis!", error_message)
        QMessageBox.critical(self, "Analysis Error", error_message)
    
    def _continue_to_payment(self):
        """Continues to the payment screen."""
        payment_data = self.model.get_payment_data()
        if not payment_data:
            QMessageBox.warning(self, "Please Wait", "Cost calculation is still in progress.")
            return
        
        # Check paper availability before proceeding to payment
        total_pages = len(payment_data['selected_pages']) * payment_data['copies']
        admin_screen = self.main_app.admin_screen
        
        if hasattr(admin_screen, 'get_paper_count'):
            available_paper = admin_screen.get_paper_count()
            
            if available_paper < total_pages:
                # Disable continue button and show warning
                self.view.set_continue_button_enabled(False)
                self.view.show_paper_warning(available_paper, total_pages)
                return
        
        self.main_app.payment_screen.set_payment_data(payment_data)
        self.main_app.show_screen('payment')
    
    def _go_back(self):
        """Goes back to the file browser screen."""
        print("Print options screen: going back to file browser")
        self.on_leave()
        self.main_app.show_screen('file_browser')
    
    def _show_message(self, title, text):
        """Shows a message to the user."""
        QMessageBox.information(self, title, text)
    
    # --- Public API for main_app ---
    
    def set_pdf_data(self, pdf_data, selected_pages):
        """Sets the PDF data and selected pages for printing."""
        self.model.set_pdf_data(pdf_data, selected_pages)
        self.view.update_copies_display(self.model.get_copies())
        self.view.set_bw_mode()
        # Clear any existing warnings when setting new PDF data
        self.view.clear_paper_warning()
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Print options screen entered")
        # Ensure analysis thread is not running from previous visits
        self.model.stop_analysis()
        
        # Clear any existing paper warnings first
        self.view.clear_paper_warning()
        
        # Delay the supplies check slightly to ensure admin_screen is ready
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.check_supplies)
        # Paper availability check will happen automatically after analysis completes

    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("Print options screen leaving")
        self.model.stop_analysis()
    
    def check_supplies(self):
        """Check current supplies status and update view."""
        try:
            # Get db_manager only when needed
            if hasattr(self.main_app, 'admin_screen') and hasattr(self.main_app.admin_screen, 'db_manager'):
                db_manager = self.main_app.admin_screen.db_manager
                status = db_manager.get_supplies_status()
                
                if status:
                    self.view.update_supplies_status(status)
                    
                    # Add warning if insufficient change possible
                    if hasattr(self.model, 'total_cost'):
                        change_needed = self._calculate_max_change(self.model.total_cost)
                        available_change = (
                            status['coins']['peso_1'] + 
                            status['coins']['peso_5'] * 5
                        )
                        
                        if available_change < change_needed:
                            status['warnings'].append(
                                f"Insufficient change available for ₱{change_needed} transaction!"
                            )
                            self.view.update_supplies_status(status)
            else:
                print("Warning: Database manager not available for supplies check")
                
        except Exception as e:
            print(f"Error checking supplies status: {e}")
            # Don't block the UI if supplies check fails
            pass

    def _check_paper_availability(self):
        """Checks if there's enough paper for the current print job."""
        payment_data = self.model.get_payment_data()
        if not payment_data:
            print("Paper check: No payment data available yet")
            return  # No payment data available yet
        
        total_pages = len(payment_data['selected_pages']) * payment_data['copies']
        admin_screen = self.main_app.admin_screen
        
        if hasattr(admin_screen, 'get_paper_count'):
            available_paper = admin_screen.get_paper_count()
            print(f"Paper check: Available={available_paper}, Required={total_pages}")
            
            if available_paper < total_pages:
                # Show warning and disable continue button
                print(f"Paper check: Showing insufficient paper warning")
                self.view.show_paper_warning(available_paper, total_pages)
            else:
                # Clear any existing warning
                print(f"Paper check: Sufficient paper available, clearing any warnings")
                self.view.clear_paper_warning()
        else:
            print("Paper check: Admin screen not available")
    
    def _calculate_max_change(self, cost):
        """Calculate maximum possible change needed for a transaction."""
        next_bill = 20  # Assuming minimum bill is ₱20
        while next_bill < cost:
            next_bill += 20
        return next_bill - cost
