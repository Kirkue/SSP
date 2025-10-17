# screens/admin/controller.py

import os
from PyQt5.QtWidgets import QWidget, QGridLayout

from .model import AdminModel
from .view import AdminScreenView

class AdminController(QWidget):
    """Manages the Admin screen's logic and UI."""
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = AdminModel()
        # Pass the background image path to the view
        background_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'assets', 'admin_panel_screen background.png')
        self.view = AdminScreenView(background_path)
        
        # Connect to database thread manager if available
        if hasattr(main_app, 'db_threader'):
            self._connect_to_database_thread_manager()

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view, 0, 0)
        
        self._connect_signals()

    # --- NEW PROPERTY TO FIX THE ERROR ---
    @property
    def db_manager(self):
        """Provides access to the model's database manager instance."""
        return self.model.db_manager
    # ------------------------------------

    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller/Model ---
        self.view.back_clicked.connect(self._go_back)
        self.view.view_data_logs_clicked.connect(self._show_data_viewer)
        self.view.paper_decreased.connect(self.model.decrease_paper_count)
        self.view.paper_increased.connect(self.model.increase_paper_count)
        self.view.reset_paper_clicked.connect(self.model.reset_paper_count)
        self.view.coin_1_decreased.connect(self.model.decrease_coin_1_count)
        self.view.coin_1_increased.connect(self.model.increase_coin_1_count)
        self.view.coin_5_decreased.connect(self.model.decrease_coin_5_count)
        self.view.coin_5_increased.connect(self.model.increase_coin_5_count)
        self.view.reset_coins_clicked.connect(self.model.reset_coin_counts)
        self.view.update_cmyk_clicked.connect(self.model.update_cmyk_levels)
        self.view.reset_cmyk_clicked.connect(self.model.reset_cmyk_levels)
        self.view.refresh_cmyk_clicked.connect(self.model.refresh_cmyk_levels)
        
        # --- Model -> View ---
        self.model.paper_count_changed.connect(self.view.update_paper_count_display)
        self.model.coin_count_changed.connect(self.view.update_coin_count_display)
        self.model.cmyk_levels_changed.connect(self.view.update_cmyk_display)
        self.model.show_message.connect(self.view.show_message_box)
    
    def _connect_to_database_thread_manager(self):
        """Connect to database thread manager for real-time updates."""
        if hasattr(self.main_app, 'db_threader'):
            # Connect CMYK level updates from database thread
            self.main_app.db_threader.cmyk_levels_updated.connect(self._on_cmyk_levels_updated)
            print("Admin screen connected to database thread manager")
    
    def _on_cmyk_levels_updated(self, cmyk_data):
        """Handle CMYK levels updated from database thread."""
        print(f"Admin screen received CMYK update: {cmyk_data}")
        if cmyk_data:
            self.model.cmyk_levels_changed.emit(
                cmyk_data['cyan'],
                cmyk_data['magenta'], 
                cmyk_data['yellow'],
                cmyk_data['black']
            )

    # --- Public API for main_app and other screens ---
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("Admin screen entered. Refreshing data.")
        self.model.load_paper_count()
        self.model.load_coin_counts()
        self.model.load_cmyk_levels()
        # Debug: Show what paper count is loaded
        print(f"Admin on_enter: Paper count loaded as {self.model.paper_count}")
        print(f"Admin on_enter: Fresh DB value: {self.model.db_manager.get_setting('paper_count', default=100)}")
    
    def refresh_cmyk_levels(self):
        """Manually refresh CMYK levels from database."""
        print("Manually refreshing CMYK levels...")
        self.model.load_cmyk_levels()

    def get_paper_count(self) -> int:
        """Returns the current paper count from the model."""
        # Always get fresh data from database to ensure consistency
        fresh_count = self.model.db_manager.get_setting('paper_count', default=100)
        print(f"Admin get_paper_count: Returning {fresh_count} (model has {self.model.paper_count})")
        return fresh_count

    def check_paper_availability(self, pages_to_print: int) -> bool:
        """
        Public method to check paper availability without decrementing.
        """
        return self.model.check_paper_availability(pages_to_print)

    def update_paper_count(self, pages_to_print: int) -> bool:
        """
        Public method for PaymentScreen to call. Delegates logic to the model.
        """
        return self.model.decrement_paper_count(pages_to_print)

    # --- Private navigation methods ---

    def _go_back(self):
        self.main_app.show_screen('idle')

    def _show_data_viewer(self):
        """Navigate to data viewer screen with error handling."""
        try:
            if hasattr(self.main_app, 'data_viewer_screen') and self.main_app.data_viewer_screen is not None:
                self.main_app.show_screen('data_viewer')
            else:
                print("❌ Data viewer screen is not available")
                self.view.show_message_box("Error", "Data viewer is not available. Please restart the application.")
        except Exception as e:
            print(f"❌ ERROR: Failed to show data viewer: {e}")
            self.view.show_message_box("Error", f"Failed to open data viewer: {str(e)}")