from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from .model import FileBrowserModel
from .view import FileBrowserView

class FileBrowserController(QWidget):
    """Controller for the File Browser screen - coordinates between model and view."""
    
    # Signals for external communication
    pdf_selected = pyqtSignal(dict)  # pdf_data
    
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        self.model = FileBrowserModel()
        self.view = FileBrowserView()
        
        # Setup timeout timer (1 minute = 60000ms)
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)
        
        # Set the view's layout as this controller's layout
        self.setLayout(self.view.main_layout)
        
        self._connect_signals()
        self._load_pdf_files()
    
    def _connect_signals(self):
        """Connect signals from the view to the model and vice-versa."""
        # --- View -> Controller -> Model ---
        self.view.back_to_idle_clicked.connect(self._go_back_to_idle)
        self.view.continue_button_clicked.connect(self._continue_to_payment)
        self.view.pdf_button_clicked.connect(self.model.select_pdf)
        
        # Reset timeout on user interaction
        self.view.back_to_idle_clicked.connect(self._reset_timeout)
        self.view.continue_button_clicked.connect(self._reset_timeout)
        self.view.pdf_button_clicked.connect(self._reset_timeout)
        
        self.view.single_page_clicked.connect(self._set_single_page_view)
        self.view.multipage_clicked.connect(self._set_multipage_view)
        self.view.select_all_clicked.connect(self._select_all_pages)
        self.view.deselect_all_clicked.connect(self._deselect_all_pages)
        self.view.prev_page_clicked.connect(self._prev_page)
        self.view.next_page_clicked.connect(self._next_page)
        self.view.prev_grid_page_clicked.connect(self._prev_grid_page)
        self.view.next_grid_page_clicked.connect(self._next_grid_page)
        self.view.page_widget_clicked.connect(self._page_widget_clicked)
        self.view.page_checkbox_clicked.connect(self._page_checkbox_clicked)
        self.view.single_page_checkbox_clicked.connect(self._single_page_checkbox_clicked)
        
        # --- Model -> Controller -> View ---
        self.model.files_loaded.connect(self.view.load_pdf_files)
        self.model.pdf_selected.connect(self.view.select_pdf)
        self.model.pdf_analysis_started.connect(self.view.show_analysis_loading)
        self.model.pdf_analysis_completed.connect(self._on_analysis_complete)
        self.model.navigation_requested.connect(self._handle_navigation)
        self.model.error_occurred.connect(self._show_error)
    
    def _load_pdf_files(self):
        """Loads PDF files from USB drive."""
        self.model.load_pdf_files()
    
    def _go_back_to_idle(self):
        """Handle back to idle button click - navigate to idle screen."""
        self.main_app.show_screen('idle')
    
    def _continue_to_payment(self):
        """Handles continue to print options button click."""
        print(f"🔍 Continue button clicked")
        print(f"🔍 Selected PDF: {self.view.selected_pdf}")
        print(f"🔍 Selected pages: {self.view.selected_pages}")
        
        if not self.view.selected_pdf:
            QMessageBox.warning(self, "No PDF Selected", "Please select a PDF file.")
            return
        
        # Get selected pages from the view
        selected_pages_list = [page for page, selected in self.view.selected_pages.items() if selected]
        print(f"🔍 Selected pages list: {selected_pages_list}")
        
        if not selected_pages_list:
            QMessageBox.warning(self, "No Pages Selected", "Please select at least one page to print.")
            return
        
        # Pass data to print options screen
        print(f"🔍 Calling set_pdf_data with PDF: {self.view.selected_pdf['filename']} and pages: {selected_pages_list}")
        options_screen = self.main_app.printing_options_screen
        options_screen.set_pdf_data(self.view.selected_pdf, selected_pages_list)
        print(f"🔍 Switching to print options screen")
        self.main_app.show_screen('printing_options')
    
    def _on_analysis_complete(self, pdf_data, analysis_data):
        """Handles completion of PDF analysis."""
        self._current_analysis = analysis_data
        self.view.update_analysis_info(analysis_data)
        self.view.set_continue_button_enabled(True)
    
    def _handle_navigation(self, screen_name):
        """Handles navigation requests from the model."""
        if hasattr(self.main_app, 'show_screen'):
            self.main_app.show_screen(screen_name)
    
    def _show_error(self, error_message):
        """Shows error messages to the user."""
        QMessageBox.critical(self, "Error", error_message)
    
    
    # --- PDF Preview Control Methods ---
    
    def _zoom_in(self):
        """Handles zoom in button click."""
        if hasattr(self.view, 'single_page_preview'):
            self.view.single_page_preview.zoomIn()
            self.view.update_zoom_label()
    
    def _zoom_out(self):
        """Handles zoom out button click."""
        if hasattr(self.view, 'single_page_preview'):
            self.view.single_page_preview.zoomOut()
            self.view.update_zoom_label()
    
    def _zoom_reset(self):
        """Handles zoom reset button click."""
        if hasattr(self.view, 'single_page_preview'):
            self.view.single_page_preview.resetZoom()
            self.view.update_zoom_label()
    
    def _set_single_page_view(self):
        """Handles single page view button click."""
        self.view.set_single_page_view()
    
    def _set_multipage_view(self):
        """Handles multipage view button click."""
        self.view.set_all_pages_view()
    
    def _select_all_pages(self):
        """Handles select all pages button click."""
        self.view.select_all_pages()
    
    def _deselect_all_pages(self):
        """Handles deselect all pages button click."""
        self.view.deselect_all_pages()
    
    def _prev_page(self):
        """Handles previous page button click."""
        if self.view.single_page_index > 1:
            self.view.single_page_index -= 1
            self.view.show_single_page()
    
    def _next_page(self):
        """Handles next page button click."""
        if self.view.selected_pdf and self.view.single_page_index < self.view.selected_pdf['pages']:
            self.view.single_page_index += 1
            self.view.show_single_page()
    
    def _prev_grid_page(self):
        """Handles previous grid page button click."""
        if self.view.current_grid_page > 1:
            self.view.current_grid_page -= 1
            self.view.show_pdf_preview()
    
    def _next_grid_page(self):
        """Handles next grid page button click."""
        if not self.view.selected_pdf:
            return
        total_doc_pages = self.view.selected_pdf['pages']
        total_grid_pages = (total_doc_pages + self.view.ITEMS_PER_GRID_PAGE - 1) // self.view.ITEMS_PER_GRID_PAGE
        if self.view.current_grid_page < total_grid_pages:
            self.view.current_grid_page += 1
            self.view.show_pdf_preview()
    
    def _page_widget_clicked(self, page_num):
        """Handles page widget click."""
        self.view.single_page_index = page_num
        self.view.set_single_page_view()
    
    def _page_checkbox_clicked(self, page_num, selected):
        """Handles page checkbox click."""
        self.view.selected_pages[page_num] = selected
        if self.view.selected_pdf:
            self.view.pdf_page_selections[self.view.selected_pdf['path']] = self.view.selected_pages.copy()
        self.view.update_selected_count()
        if self.view.view_mode == 'single' and page_num == self.view.single_page_index:
            self.view.single_page_checkbox.blockSignals(True)
            self.view.single_page_checkbox.setChecked(selected)
            self.view.single_page_checkbox.blockSignals(False)
    
    def _single_page_checkbox_clicked(self, selected):
        """Handles single page checkbox click."""
        if self.view.selected_pdf:
            self.view.selected_pages[self.view.single_page_index] = selected
            self.view.pdf_page_selections[self.view.selected_pdf['path']] = self.view.selected_pages.copy()
            self.view.update_selected_count()
    
    def load_pdf_files(self, pdf_files):
        """Public method to load PDF files from external sources (like USB controller)."""
        self.model.load_pdf_files(pdf_files)
    
    def on_enter(self):
        """Called by main_app when this screen becomes active."""
        print("File browser screen entered")
        # Don't reload PDF files here - they are loaded by USB controller
        # The files are already loaded via load_pdf_files() method
        
        # Start timeout timer (1 minute)
        self.timeout_timer.start(60000)
        print("⏰ File browser screen timeout started (1 minute)")
    
    def on_leave(self):
        """Called by main_app when leaving this screen."""
        print("File browser screen leaving")
        self.model.cleanup()
        # Stop timeout timer
        self.timeout_timer.stop()
    
    def _on_timeout(self):
        """Handle timeout - return to idle screen."""
        print("⏰ File browser screen timeout - returning to idle screen")
        self.main_app.show_screen('idle')
    
    def _reset_timeout(self):
        """Reset the timeout timer (call on user activity)."""
        self.timeout_timer.stop()
        self.timeout_timer.start(60000)
        print("⏰ File browser screen timeout reset")
