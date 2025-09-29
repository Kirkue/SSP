# screens/admin/controller.py

from PyQt5.QtWidgets import QWidget, QGridLayout

from .model import AdminModel
from .view import AdminScreenView

class AdminController(QWidget):
    """Manages the Admin screen's logic and UI."""
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

        self.model = AdminModel()
        self.view = AdminScreenView()

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
        self.view.reset_paper_clicked.connect(self.model.reset_paper_count)
        self.view.update_paper_clicked.connect(self.model.update_paper_count_from_string)
        self.view.update_coin_1_clicked.connect(self.model.update_coin_1_count)
        self.view.update_coin_5_clicked.connect(self.model.update_coin_5_count)
        self.view.reset_coins_clicked.connect(self.model.reset_coin_counts)
        self.view.update_cmyk_clicked.connect(self.model.update_cmyk_levels)
        self.view.reset_cmyk_clicked.connect(self.model.reset_cmyk_levels)
        
        # --- Model -> View ---
        self.model.paper_count_changed.connect(self.view.update_paper_count_display)
        self.model.coin_count_changed.connect(self.view.update_coin_count_display)
        self.model.cmyk_levels_changed.connect(self.view.update_cmyk_display)
        self.model.show_message.connect(self.view.show_message_box)

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

    def get_paper_count(self) -> int:
        """Returns the current paper count from the model."""
        # Always get fresh data from database to ensure consistency
        fresh_count = self.model.db_manager.get_setting('paper_count', default=100)
        print(f"Admin get_paper_count: Returning {fresh_count} (model has {self.model.paper_count})")
        return fresh_count

    def update_paper_count(self, pages_to_print: int) -> bool:
        """
        Public method for PaymentScreen to call. Delegates logic to the model.
        """
        return self.model.decrement_paper_count(pages_to_print)

    # --- Private navigation methods ---

    def _go_back(self):
        self.main_app.show_screen('idle')

    def _show_data_viewer(self):
        self.main_app.show_screen('data_viewer')