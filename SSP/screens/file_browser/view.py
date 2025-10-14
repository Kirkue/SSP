import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QFrame, QMessageBox, QGridLayout, QCheckBox, QSizePolicy, QStackedLayout, QSpacerItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QPoint
from PyQt5.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QTouchEvent
from .pdf_preview_widget import PDFPreviewWidget

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("PyMuPDF not available - PDF preview will be limited")

def get_base_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class DragScrollArea(QScrollArea):
    """Custom scroll area that supports mouse drag scrolling."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragging = False
        self.last_drag_position = QPoint()
        self.setMouseTracking(True)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_drag_position = event.globalPos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.last_drag_position
            # More responsive scrolling for touch screens
            scroll_value = self.verticalScrollBar().value() - delta.y()
            self.verticalScrollBar().setValue(scroll_value)
            self.last_drag_position = event.globalPos()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event):
        """Handle mouse wheel scrolling."""
        delta = event.angleDelta().y()
        scroll_amount = delta // 8  # Adjust scroll sensitivity
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - scroll_amount
        )
        event.accept()
    
    def enterEvent(self, event):
        """Change cursor when entering the scroll area."""
        if not self.dragging:
            self.setCursor(Qt.OpenHandCursor)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Reset cursor when leaving the scroll area."""
        if not self.dragging:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)
    
    def touchEvent(self, event):
        """Handle touch events for touch screens."""
        if event.touchPoints():
            touch_point = event.touchPoints()[0]
            if event.type() == QTouchEvent.TouchBegin:
                self.dragging = True
                self.last_drag_position = touch_point.pos().toPoint()
            elif event.type() == QTouchEvent.TouchUpdate and self.dragging:
                delta = touch_point.pos().toPoint() - self.last_drag_position
                scroll_value = self.verticalScrollBar().value() - delta.y()
                self.verticalScrollBar().setValue(scroll_value)
                self.last_drag_position = touch_point.pos().toPoint()
            elif event.type() == QTouchEvent.TouchEnd:
                self.dragging = False
        event.accept()

class PDFButton(QPushButton):
    pdf_selected = pyqtSignal(dict)
    
    def __init__(self, pdf_data):
        super().__init__()
        self.pdf_data = pdf_data
        self.is_selected = False
        filename = pdf_data['filename']
        size_mb = pdf_data.get('size', 0) / (1024 * 1024)
        pages = pdf_data.get('pages', 1)
        self.setText(f"📄 {filename}\n({size_mb:.1f}MB, ~{pages} pages)")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet(self.get_normal_style())
        self.clicked.connect(self.on_click)
        self.setMinimumWidth(280)
        self.setFixedHeight(60)

    def get_normal_style(self):
        return """
            QPushButton {
                background-color: #1e440a; color: #fff; border: 1px solid #555;
                border-radius: 8px; padding: 10px; text-align: left;
                font-size: 13px; margin: 2px; height: 60px;
            }
            QPushButton:hover { background-color: #2a5d1a; border: 1px solid #36454F; }
        """

    def get_selected_style(self):
        return """
            QPushButton {
                background-color: #4d80cc; color: #fff; border: 3px solid #6699ff;
                border-radius: 8px; padding: 10px; text-align: left;
                font-size: 13px; font-weight: bold; margin: 2px; height: 60px;
            }
        """

    def on_click(self): 
        self.pdf_selected.emit(self.pdf_data)
    
    def set_selected(self, selected):
        self.is_selected = selected
        if selected: 
            self.setStyleSheet(self.get_selected_style())
        else: 
            self.setStyleSheet(self.get_normal_style())

class PDFPageWidget(QFrame):
    page_selected = pyqtSignal(int)
    page_checkbox_clicked = pyqtSignal(int, bool)
    def __init__(self, page_num=1, checked=True):
        super().__init__()
        self.page_num = page_num
        self._original_pixmap = None
        # Allow the page widget to expand to fill available space
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setup_ui(checked)
        
    def setup_ui(self, checked):
        self.setStyleSheet("QFrame { background-color: white; border: 2px solid #ddd; border-radius: 8px; margin: 4px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.checkbox = QCheckBox(f"Page {self.page_num}")
        self.checkbox.setChecked(checked)
        self.checkbox.setStyleSheet("""
            QCheckBox { 
                color: #36454F; 
                font-size: 14px; 
                font-weight: bold;
                padding: 4px 2px 6px 2px;
                min-height: 26px;
            }
            QCheckBox::indicator { 
                width: 20px; 
                height: 20px; 
                border-radius: 4px;
            }
            QCheckBox::indicator:checked { 
                background-color: #4CAF50; 
                border: 2px solid #4CAF50; 
            }
            QCheckBox::indicator:unchecked { 
                background-color: white; 
                border: 2px solid #ccc; 
            }
        """)
        self.checkbox.clicked.connect(self.on_checkbox_clicked)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(160)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setStyleSheet("QLabel { background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 4px; color: #36454F; font-size: 10px; }")
        self.preview_label.setText(f"Loading\nPage {self.page_num}...")
        layout.addWidget(self.checkbox, 0)
        layout.addWidget(self.preview_label, 1)
        self.setMouseTracking(True)
        
    def mousePressEvent(self, event):
        if not self.checkbox.geometry().contains(event.pos()): 
            self.page_selected.emit(self.page_num)
        
    def on_checkbox_clicked(self, checked):
        self.page_checkbox_clicked.emit(self.page_num, checked)
        if checked: 
            self.setStyleSheet("QFrame { background-color: white; border: 3px solid #4CAF50; border-radius: 8px; margin: 4px; }")
        else: 
            self.setStyleSheet("QFrame { background-color: #f5f5f5; border: 2px solid #ccc; border-radius: 8px; margin: 4px; }")
        
    def set_preview_image(self, pixmap):
        # Store original pixmap and scale to fit current label size
        self._original_pixmap = pixmap
        self._update_scaled_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Rescale preview on resize to fill available space
        if self._original_pixmap is not None:
            self._update_scaled_preview()

    def _update_scaled_preview(self):
        if self._original_pixmap is None:
            return
        label_size = self.preview_label.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        scaled = self._original_pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        
    def set_error_message(self, error_msg):
        self.preview_label.setText(f"Page {self.page_num}\n\nError:\n{error_msg}")
        self.preview_label.setStyleSheet("QLabel { background-color: #ffeeee; border: 1px solid #ffaaaa; border-radius: 4px; color: #cc0000; font-size: 9px; }")

class PDFPreviewThread(QThread):
    preview_ready = pyqtSignal(int, QPixmap)
    error_occurred = pyqtSignal(int, str)
    def __init__(self, pdf_path, pages_to_render: list):
        super().__init__()
        self.pdf_path = pdf_path
        self.pages_to_render = pages_to_render
        self.running = True
        
    def run(self):
        if not PYMUPDF_AVAILABLE:
            for page_num in self.pages_to_render:
                if not self.running: 
                    break
                self.error_occurred.emit(page_num, "PyMuPDF not available")
            return
        try:
            doc = fitz.open(self.pdf_path)
            for page_num in self.pages_to_render:
                if not self.running: 
                    break
                try:
                    page = doc[page_num - 1]
                    # Render at higher resolution to avoid pixelation in previews
                    target_height_px = 1000  # target preview rendering height
                    page_height_pts = max(1.0, page.rect.height)
                    scale = min(5.0, max(1.5, target_height_px / page_height_pts))
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimg)
                    self.preview_ready.emit(page_num, pixmap)
                except Exception as e: 
                    self.error_occurred.emit(page_num, str(e))
            doc.close()
        except Exception as e:
            err_page = self.pages_to_render[0] if self.pages_to_render else 1
            self.error_occurred.emit(err_page, f"Failed to open PDF: {str(e)}")
            
    def stop(self): 
        self.running = False

class FileBrowserView(QWidget):
    """View for the File Browser screen - handles UI components and presentation."""
    
    SINGLE_PAGE_PREVIEW_WIDTH = 280
    SINGLE_PAGE_PREVIEW_HEIGHT = 380
    ITEMS_PER_GRID_PAGE = 3

    # Signals for user interactions
    back_button_clicked = pyqtSignal()
    continue_button_clicked = pyqtSignal()
    pdf_button_clicked = pyqtSignal(dict)  # pdf_data
    single_page_clicked = pyqtSignal()
    multipage_clicked = pyqtSignal()
    select_all_clicked = pyqtSignal()
    deselect_all_clicked = pyqtSignal()
    prev_page_clicked = pyqtSignal()
    next_page_clicked = pyqtSignal()
    prev_grid_page_clicked = pyqtSignal()
    next_grid_page_clicked = pyqtSignal()
    page_widget_clicked = pyqtSignal(int)
    page_checkbox_clicked = pyqtSignal(int, bool)
    single_page_checkbox_clicked = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_files_data = []
        self.selected_pdf = None
        self.pdf_buttons = []
        self.page_widgets = []
        self.page_widget_map = {}
        self.selected_pages = None
        self.pdf_page_selections = {}
        self.preview_thread = None
        self.view_mode = 'all'
        self.single_page_index = 1
        self.current_grid_page = 1
        self.setup_ui()

    def setup_ui(self):
        """Sets up the user interface for the screen."""
        stacked_layout = QStackedLayout()
        stacked_layout.setContentsMargins(0, 0, 0, 0)
        stacked_layout.setStackingMode(QStackedLayout.StackAll)

        background_label = QLabel()
        base_dir = get_base_dir()
        image_path = os.path.join(base_dir, 'assets', 'file_browser_screen background.png')
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            background_label.setPixmap(pixmap)
            background_label.setScaledContents(True)
        else:
            background_label.setStyleSheet("background-color: #1f1f38;")

        foreground_widget = QWidget()
        foreground_widget.setStyleSheet("background-color: transparent;")
        main_col = QVBoxLayout(foreground_widget)
        main_col.setContentsMargins(0, 0, 0, 0)
        main_col.setSpacing(0)

        split_row = QHBoxLayout()
        split_row.setContentsMargins(0, 0, 0, 0)
        split_row.setSpacing(0)

        # LEFT PANEL
        left_panel = QFrame()
        left_panel.setFixedWidth(360) 
        left_panel.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 0, 10, 20)
        left_layout.setSpacing(10) 
        left_layout.addSpacing(65) 
        self.file_header = QLabel("PDF Files (0 files)")
        self.file_header.setStyleSheet("QLabel { color: #36454F; font-size: 16px; font-weight: bold; background-color: transparent; padding-left: 13px;}")
        self.file_header.setFixedHeight(32)
        left_layout.addWidget(self.file_header, 0, Qt.AlignLeft)
        # File list container with scroll area and navigation buttons
        file_container = QWidget()
        file_container.setStyleSheet("background-color: transparent;")
        file_container_layout = QVBoxLayout(file_container)
        file_container_layout.setContentsMargins(0, 0, 0, 0)
        file_container_layout.setSpacing(5)
        
        # Up button (hidden since we're using scroll bar)
        self.file_up_btn = QPushButton("▲ Previous Files")
        self.file_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e440a;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: #2a5d1a;
            }
            QPushButton:disabled {
                background-color: #666666;
                color: #999999;
            }
        """)
        self.file_up_btn.setFixedHeight(60)
        self.file_up_btn.setEnabled(False)
        self.file_up_btn.hide()  # Hide since we're using scroll bar
        file_container_layout.addWidget(self.file_up_btn)
        
        # Scroll area for file list
        file_scroll = QScrollArea()
        file_scroll.setWidgetResizable(True)
        file_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        file_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Keep viewport margin default so content width is unchanged
        file_scroll.setViewportMargins(0, 0, 0, 0)
        file_scroll.setStyleSheet("""
            QScrollArea { 
                border: none; 
                background-color: transparent; 
            }
            /* Rounded, lighter track without borders */
            QScrollBar:vertical { 
                background-color: #d9d9d9; /* visible track color */
                width: 32px; 
                border: none; 
                border-radius: 8px; 
                margin: 2px; 
            }
            QScrollBar::groove:vertical { 
                background-color: #d9d9d9; /* lighter than handle */
                border: none; 
                border-radius: 8px; 
                margin: 2px; 
            }
            /* Rounded handle */
            QScrollBar::handle:vertical { 
                background-color: #666; 
                border: none; 
                border-radius: 8px; 
                min-height: 30px; 
                margin: 2px; 
            }
            QScrollBar::handle:vertical:hover { 
                background-color: #888; 
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { 
                height: 0px; 
                border: none; 
                background: transparent; 
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { 
                background: transparent; 
            }
        """)
        
        # File list widget
        self.file_list_widget = QWidget()
        self.file_list_widget.setStyleSheet("background-color: transparent;")
        self.file_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_layout.setContentsMargins(5, 5, 5, 5)
        self.file_list_layout.setSpacing(8)
        self.file_list_layout.addStretch()
        file_scroll.setWidget(self.file_list_widget)
        file_container_layout.addWidget(file_scroll)
        
        # Down button (hidden since we're using scroll bar)
        self.file_down_btn = QPushButton("▼ More Files")
        self.file_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e440a;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                margin: 2px;
            }
            QPushButton:hover {
                background-color: #2a5d1a;
            }
            QPushButton:disabled {
                background-color: #666666;
                color: #999999;
            }
        """)
        self.file_down_btn.setFixedHeight(60)
        self.file_down_btn.setEnabled(False)
        self.file_down_btn.hide()  # Hide since we're using scroll bar
        file_container_layout.addWidget(self.file_down_btn)
        
        left_layout.addWidget(file_container)
        split_row.addWidget(left_panel)

        # RIGHT PANEL
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: transparent;")
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 20, 12)
        right_panel_layout.setSpacing(10)

        right_panel_layout.addSpacing(65)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        header_row.setContentsMargins(20, 0, 20, 0)

        self.preview_header = QLabel("Select a PDF file to preview pages")
        self.preview_header.setStyleSheet("QLabel { color: #36454F; font-size: 18px; font-weight: bold; background-color: transparent; }")
        self.preview_header.setFixedHeight(32)
        button_height = 40

        all_button_style = f"""
            QPushButton {{
                color: white; font-size: 12px; font-weight: bold;
                border: none; border-radius: 4px !important; height: {button_height}px;
                background-color: #1e440a;
                padding-left: 12px; padding-right: 12px;
            }}
            QPushButton:checked, QPushButton:hover {{ background-color: #2a5d1a; }}
        """

        self.view_all_btn = QPushButton("All Pages View")
        self.view_single_btn = QPushButton("Single Page View")
        self.view_all_btn.setCheckable(True)
        self.view_single_btn.setCheckable(True)
        self.view_all_btn.setChecked(True)
        self.view_all_btn.setStyleSheet(all_button_style)
        self.view_single_btn.setStyleSheet(all_button_style)
        self.view_all_btn.setFixedHeight(button_height)
        self.view_single_btn.setFixedHeight(button_height)
        self.view_all_btn.clicked.connect(self.multipage_clicked.emit)
        self.view_single_btn.clicked.connect(self.single_page_clicked.emit)

        self.select_all_btn = QPushButton("Select All Pages")
        self.select_all_btn.setVisible(False)
        self.select_all_btn.setStyleSheet(all_button_style)
        self.select_all_btn.setFixedHeight(button_height)
        self.select_all_btn.clicked.connect(self.select_all_clicked.emit)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.setVisible(False)
        self.deselect_all_btn.setStyleSheet("""
            QPushButton {
                color: white; font-size: 12px; font-weight: bold;
                border: none; border-radius: 4px; height: 40px;
                background-color: #ff9800; padding-left: 12px; padding-right: 12px;
            }
            QPushButton:hover, QPushButton:checked { background-color: #f57c00; }
        """)
        self.deselect_all_btn.setFixedHeight(button_height)
        self.deselect_all_btn.clicked.connect(self.deselect_all_clicked.emit)

        header_row.addWidget(self.preview_header, 1, Qt.AlignLeft)
        header_row.addWidget(self.view_all_btn)
        header_row.addWidget(self.view_single_btn)
        header_row.addWidget(self.select_all_btn)
        header_row.addWidget(self.deselect_all_btn)
        
        # PREVIEW CONTAINER
        self.preview_container = QFrame()
        self.preview_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_container.setStyleSheet("QFrame { border: 2px solid #0f1f00; border-radius: 6px; background-color: #fffff; }")
        
        self.preview_layout = QGridLayout(self.preview_container)
        self.preview_layout.setSpacing(8)
        # Minimize outer gutters and maximize the three content columns
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview_layout.setColumnStretch(0, 0) # Left gutter
        self.preview_layout.setColumnStretch(1, 1) # Content 1
        self.preview_layout.setColumnStretch(2, 1) # Content 2
        self.preview_layout.setColumnStretch(3, 1) # Content 3
        self.preview_layout.setColumnStretch(4, 0) # Right gutter
        # Use a single content row that takes all height
        self.preview_layout.setRowStretch(0, 1)

        # SINGLE PAGE VIEW CONTAINER (only the preview lives here to maximize height)
        self.single_page_widget = QWidget()
        self.single_page_widget.setStyleSheet("background-color: #c4c4c4;") 
        self.single_page_layout = QVBoxLayout(self.single_page_widget)
        self.single_page_layout.setSpacing(8)
        self.single_page_layout.setAlignment(Qt.AlignVCenter)
        self.single_page_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.single_page_preview = PDFPreviewWidget()
        # Expand to fill available space and fit entire page in view
        self.single_page_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.single_page_layout.addWidget(self.single_page_preview, 1)

        # PAGINATION CONTROLS
        self.prev_grid_page_btn = QPushButton("<< Prev")
        self.next_grid_page_btn = QPushButton("Next >>")
        pagination_style = f"""
            QPushButton {{
                color: white; font-size: 12px; font-weight: bold; border: none; border-radius: 4px; height: {button_height}px;
                background-color: #1e440a; padding-left: 12px; padding-right: 12px;
            }}
            QPushButton:hover, QPushButton:checked {{ background-color: #2a5d1a; }}
            QPushButton:disabled {{ background-color: #3e423a; color: #555; }}
        """
        self.prev_grid_page_btn.setStyleSheet(pagination_style)
        self.next_grid_page_btn.setStyleSheet(pagination_style)
        self.prev_grid_page_btn.setFixedHeight(button_height)
        self.next_grid_page_btn.setFixedHeight(button_height)
        self.prev_grid_page_btn.clicked.connect(self.prev_grid_page_clicked.emit)
        self.next_grid_page_btn.clicked.connect(self.next_grid_page_clicked.emit)
        self.grid_page_label = QLabel("Page 1 / 1")
        self.grid_page_label.setAlignment(Qt.AlignCenter)
        self.grid_page_label.setStyleSheet("color: #36454F; font-size: 14px; background-color: transparent;")

        # BOTTOM CONTROLS
        bottom_controls = QHBoxLayout()
        bottom_controls.setSpacing(15)
        self.back_btn = QPushButton("← Back to USB")
        self.back_btn.setStyleSheet(f"QPushButton {{ color: white; font-size: 12px; font-weight: bold; border: none; border-radius: 4px; height: {button_height}px; background-color: #ff0000; padding-left: 12px; padding-right: 12px; }} QPushButton:hover {{ background-color: #ffb84d; }}")
        self.back_btn.setFixedHeight(button_height)
        self.back_btn.clicked.connect(self.back_button_clicked.emit)
        self.continue_btn = QPushButton("Set Print Options →")
        self.continue_btn.setStyleSheet(all_button_style)
        self.continue_btn.setFixedHeight(button_height)
        self.continue_btn.clicked.connect(self.continue_button_clicked.emit)
        self.continue_btn.setVisible(False)
        self.page_info = QLabel("No PDF selected")
        self.page_info.setStyleSheet("QLabel { color: #36454F; font-size: 14px; background-color: transparent; }")
        self.selected_count_label = QLabel("")
        self.selected_count_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 14px; font-weight: bold; background-color: transparent; }")
        pagination_controls = QHBoxLayout()
        pagination_controls.setSpacing(6)
        # Grid (all-pages) pagination controls (default visible in all-pages view)
        pagination_controls.addWidget(self.prev_grid_page_btn, 0, Qt.AlignCenter)
        pagination_controls.addWidget(self.grid_page_label, 0, Qt.AlignCenter)
        pagination_controls.addWidget(self.next_grid_page_btn, 0, Qt.AlignCenter)
        # Single-page navigation controls (placed in same area, hidden by default)
        nav_btn_style = f"""
            QPushButton {{
                background-color: #1e440a; color: #fff; border: none; border-radius: 4px;
                font-size: 18px; width: 40px; height: 40px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
                padding: 0; font-weight: bold;
            }}
            QPushButton:pressed, QPushButton:checked, QPushButton:hover {{ background-color: #2a5d1a; }}
        """
        self.prev_page_btn = QPushButton("←")
        self.prev_page_btn.setStyleSheet(nav_btn_style)
        self.next_page_btn = QPushButton("→")
        self.next_page_btn.setStyleSheet(nav_btn_style)
        self.prev_page_btn.setFixedHeight(button_height)
        self.next_page_btn.setFixedHeight(button_height)
        self.prev_page_btn.clicked.connect(self.prev_page_clicked.emit)
        self.next_page_btn.clicked.connect(self.next_page_clicked.emit)
        self.page_input = QLabel("1")
        self.page_input.setStyleSheet("QLabel { background-color: transparent; color: #36454F; font-size: 13px; min-width: 40px; max-width: 40px; border-radius: 3px; padding: 1px 4px; border: none; font-weight: bold; qproperty-alignment: AlignCenter; }")
        self.single_page_checkbox = QCheckBox("Select this page")
        self.single_page_checkbox.setStyleSheet("QCheckBox { color: #36454F; font-size: 13px; background-color: transparent; }")
        self.single_page_checkbox.stateChanged.connect(lambda state: self.single_page_checkbox_clicked.emit(state == Qt.Checked))
        # Add single-page controls but hide by default
        pagination_controls.addWidget(self.prev_page_btn, 0, Qt.AlignCenter)
        pagination_controls.addWidget(self.page_input, 0, Qt.AlignCenter)
        pagination_controls.addWidget(self.next_page_btn, 0, Qt.AlignCenter)
        pagination_controls.addWidget(self.single_page_checkbox, 0, Qt.AlignCenter)
        self.prev_page_btn.hide()
        self.next_page_btn.hide()
        self.page_input.hide()
        self.single_page_checkbox.hide()
        bottom_controls.addWidget(self.back_btn, 0, Qt.AlignCenter)
        bottom_controls.addStretch(1)
        bottom_controls.addLayout(pagination_controls)
        bottom_controls.addStretch(1)
        bottom_controls.addWidget(self.page_info, 0, Qt.AlignCenter)
        bottom_controls.addWidget(self.selected_count_label, 0, Qt.AlignCenter)
        bottom_controls.addStretch(1)
        bottom_controls.addWidget(self.continue_btn, 0, Qt.AlignCenter)

        # STACKED LAYOUT FOR PREVIEW AREA
        preview_area_layout = QStackedLayout()
        preview_area_layout.setStackingMode(QStackedLayout.StackAll)
        preview_area_layout.setContentsMargins(0, 0, 0, 0)
        preview_area_layout.addWidget(self.preview_container)
        preview_area_layout.addWidget(self.single_page_widget)
        self.single_page_widget.hide()

        right_panel_layout.addLayout(header_row)
        right_panel_layout.addLayout(preview_area_layout, 1)
        right_panel_layout.addLayout(bottom_controls)
        
        # Slightly reduce the right panel stretch to give more room for the file list scrollbar
        split_row.addWidget(right_panel, 1)
        main_col.addLayout(split_row, 1)
        stacked_layout.addWidget(background_label)
        stacked_layout.addWidget(foreground_widget)
        
        # Don't set layout here - let the controller handle it
        self.main_layout = stacked_layout
        self.prev_grid_page_btn.hide()
        self.grid_page_label.hide()
        self.next_grid_page_btn.hide()

    def load_pdf_files(self, pdf_files):
        """Loads PDF files into the list."""
        print(f"📁 Loading {len(pdf_files)} PDF files into view")
        self.pdf_files_data = []
        self.pdf_page_selections = {}
        for pdf_info in pdf_files: 
            self.pdf_files_data.append({
                'filename': pdf_info['filename'], 
                'type': 'pdf', 
                'pages': pdf_info.get('pages', 1), 
                'size': pdf_info['size'], 
                'path': pdf_info['path']
            })
        self.file_header.setText(f"PDF Files ({len(self.pdf_files_data)} files)")
        self.clear_file_list()
        self.pdf_buttons = []
        for pdf_data in self.pdf_files_data:
            pdf_btn = PDFButton(pdf_data)
            pdf_btn.pdf_selected.connect(self.pdf_button_clicked.emit)
            self.pdf_buttons.append(pdf_btn)
            self.file_list_layout.insertWidget(self.file_list_layout.count() - 1, pdf_btn)
        
        # Automatically select the first file if available
        if self.pdf_files_data:
            first_pdf = self.pdf_files_data[0]
            self.selected_pdf = first_pdf
            self.selected_pages = None
            # Emit the signal to trigger preview loading
            self.pdf_button_clicked.emit(first_pdf)
        else:
            self.selected_pdf = None
            self.selected_pages = None
            self.clear_preview()
            self.page_info.setText("Select a PDF to preview pages")
            self.preview_header.setText("Select a PDF file to preview pages")
    

    def clear_file_list(self):
        """Clears the file list."""
        while self.file_list_layout.count() > 1:
            child = self.file_list_layout.takeAt(0)
            if child.widget(): 
                child.widget().deleteLater()

    def select_pdf(self, pdf_data):
        """Selects a PDF file and updates the UI."""
        print(f"📄 Selecting PDF: {pdf_data['filename']}")
        if self.selected_pdf is not None and self.selected_pages is not None: 
            self.pdf_page_selections[self.selected_pdf['path']] = self.selected_pages.copy()
        self.selected_pdf = pdf_data
        if pdf_data['path'] in self.pdf_page_selections: 
            self.selected_pages = self.pdf_page_selections[self.selected_pdf['path']].copy()
        else: 
            self.selected_pages = {i: True for i in range(1, pdf_data['pages'] + 1)}
        for btn in self.pdf_buttons: 
            btn.set_selected(btn.pdf_data == pdf_data)
        self.preview_header.setText(f"{pdf_data['filename']}")
        self.view_mode = 'all'
        self.update_view_mode_buttons()
        self.current_grid_page = 1
        self.single_page_index = 1
        self.show_pdf_preview()

    def show_pdf_preview(self):
        """Shows the PDF preview in grid mode."""
        self.preview_container.show()
        self.single_page_widget.hide()
        # Show grid pagination; hide single-page controls
        self.prev_grid_page_btn.show()
        self.grid_page_label.show()
        self.next_grid_page_btn.show()
        self.prev_page_btn.hide()
        self.next_page_btn.hide()
        self.page_input.hide()
        self.single_page_checkbox.hide()
        if not self.selected_pdf:
            self.prev_grid_page_btn.hide()
            self.grid_page_label.hide()
            self.next_grid_page_btn.hide()
            return
        self.clear_preview()
        total_doc_pages = self.selected_pdf['pages']
        self.page_info.setText("")
        self.update_selected_count()
        self.select_all_btn.setVisible(True)
        self.deselect_all_btn.setVisible(True)
        self.continue_btn.setVisible(True)
        total_grid_pages = (total_doc_pages + self.ITEMS_PER_GRID_PAGE - 1) // self.ITEMS_PER_GRID_PAGE
        self.grid_page_label.setText(f"{self.current_grid_page} / {total_grid_pages}")
        self.prev_grid_page_btn.setEnabled(self.current_grid_page > 1)
        self.next_grid_page_btn.setEnabled(self.current_grid_page < total_grid_pages)
        start_page = (self.current_grid_page - 1) * self.ITEMS_PER_GRID_PAGE + 1
        end_page = min(self.current_grid_page * self.ITEMS_PER_GRID_PAGE, total_doc_pages)
        pages_to_show = list(range(start_page, end_page + 1))
        
        for i, page_num in enumerate(pages_to_show):
            page_widget = PDFPageWidget(page_num, checked=self.selected_pages.get(page_num, True))
            page_widget.page_selected.connect(self.page_widget_clicked.emit)
            page_widget.page_checkbox_clicked.connect(self.page_checkbox_clicked.emit)
            self.page_widgets.append(page_widget)
            self.page_widget_map[page_num] = page_widget
            # Arrange a single row at row 0 with 3 columns (1..3)
            self.preview_layout.addWidget(page_widget, 0, (i % 3) + 1)
            
        if PYMUPDF_AVAILABLE:
            self.preview_thread = PDFPreviewThread(self.selected_pdf['path'], pages_to_show)
            self.preview_thread.preview_ready.connect(self.on_preview_ready)
            self.preview_thread.error_occurred.connect(self.on_preview_error)
            self.preview_thread.start()
        else:
            for widget in self.page_widgets: 
                widget.preview_label.setText(f"Page {widget.page_num}\n\nPDF Preview\nRequires PyMuPDF")

    def clear_preview(self):
        """Clears the preview area."""
        if self.preview_thread and self.preview_thread.isRunning(): 
            self.preview_thread.stop()
            self.preview_thread.wait()
        
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            
        self.page_widgets.clear()
        self.page_widget_map.clear()
        self.select_all_btn.setVisible(False)
        self.deselect_all_btn.setVisible(False)
        self.continue_btn.setVisible(False)
        self.selected_count_label.setText("")

    def show_single_page(self):
        """Shows the single page view."""
        self.preview_container.hide()
        self.single_page_widget.show()
        # Hide grid pagination; show single-page controls in bottom bar
        self.prev_grid_page_btn.hide()
        self.grid_page_label.hide()
        self.next_grid_page_btn.hide()
        self.prev_page_btn.show()
        self.next_page_btn.show()
        self.page_input.show()
        self.single_page_checkbox.show()
        if not self.selected_pdf: 
            return
        self.single_page_preview.setBorderless(True)
        total_pages = self.selected_pdf['pages']
        if not (1 <= self.single_page_index <= total_pages): 
            self.single_page_index = 1
        page_num = self.single_page_index
        self.page_info.setText(f"Page {page_num} of {total_pages}")
        self.page_input.setText(f"{page_num}")
        self.single_page_checkbox.blockSignals(True)
        self.single_page_checkbox.setChecked(self.selected_pages.get(page_num, False))
        self.single_page_checkbox.blockSignals(False)
        self.single_page_preview.clear()
        if PYMUPDF_AVAILABLE:
            try:
                doc = fitz.open(self.selected_pdf['path'])
                if page_num <= len(doc):
                    page = doc[page_num-1]
                    # Increase DPI for sharper single-page preview (from 300 to 450 DPI)
                    pix = page.get_pixmap(matrix=fitz.Matrix(450/72, 450/72), alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    self.single_page_preview.setPixmap(QPixmap.fromImage(qimg))
                doc.close()
            except Exception as e: 
                print(f"Error rendering page {page_num}: {e}")
                self.single_page_preview.clear()
        else: 
            self.single_page_preview.clear()

    def update_view_mode_buttons(self):
        """Updates the view mode buttons."""
        self.view_all_btn.setChecked(self.view_mode == 'all')
        self.view_single_btn.setChecked(self.view_mode == 'single')

    def set_all_pages_view(self):
        """Sets the view to all pages mode."""
        self.view_mode = 'all'
        self.update_view_mode_buttons()
        self.show_pdf_preview()

    def set_single_page_view(self):
        """Sets the view to single page mode."""
        self.view_mode = 'single'
        self.update_view_mode_buttons()
        if self.selected_pdf and not (1 <= self.single_page_index <= self.selected_pdf['pages']): 
            self.single_page_index = 1
        self.show_single_page()

    def update_selected_count(self):
        """Updates the selected count display."""
        if not self.selected_pages: 
            return
        selected_count = sum(1 for selected in self.selected_pages.values() if selected)
        self.selected_count_label.setText(f"Selected: {selected_count}/{len(self.selected_pages)} pages")
        self.continue_btn.setEnabled(selected_count > 0)

    def select_all_pages(self):
        """Selects all pages."""
        if not self.selected_pages: 
            return
        for page_num in self.selected_pages: 
            self.selected_pages[page_num] = True
        if self.selected_pdf: 
            self.pdf_page_selections[self.selected_pdf['path']] = self.selected_pages.copy()
        for widget in self.page_widgets: 
            widget.checkbox.setChecked(True)
        self.update_selected_count()
        if self.view_mode == 'single': 
            self.single_page_checkbox.blockSignals(True)
            self.single_page_checkbox.setChecked(True)
            self.single_page_checkbox.blockSignals(False)

    def deselect_all_pages(self):
        """Deselects all pages."""
        if not self.selected_pages: 
            return
        for page_num in self.selected_pages: 
            self.selected_pages[page_num] = False
        if self.selected_pdf: 
            self.pdf_page_selections[self.selected_pdf['path']] = self.selected_pages.copy()
        for widget in self.page_widgets: 
            widget.checkbox.setChecked(False)
        self.update_selected_count()
        if self.view_mode == 'single': 
            self.single_page_checkbox.blockSignals(True)
            self.single_page_checkbox.setChecked(False)
            self.single_page_checkbox.blockSignals(False)

    def on_preview_ready(self, page_num, pixmap):
        """Handles when a preview is ready."""
        if self.view_mode == 'all':
            widget = self.page_widget_map.get(page_num)
            if widget: 
                widget.set_preview_image(pixmap)
        elif self.view_mode == 'single' and page_num == self.single_page_index: 
            self.single_page_preview.setPixmap(pixmap)

    def on_preview_error(self, page_num, error_msg):
        """Handles when a preview error occurs."""
        if self.view_mode == 'all':
            widget = self.page_widget_map.get(page_num)
            if widget: 
                widget.set_error_message(error_msg)
        elif self.view_mode == 'single' and page_num == self.single_page_index: 
            self.single_page_preview.clear()

    def update_zoom_label(self):
        """Updates the zoom label."""
        if self.single_page_preview:
            zoom_factor = self.single_page_preview.getZoomFactor()
            self.zoom_label.setText(f"{int(zoom_factor * 100)}%")

    def set_continue_button_enabled(self, enabled):
        """Enables or disables the continue button."""
        self.continue_btn.setEnabled(enabled)

    def show_analysis_loading(self, filename):
        """Shows loading state for analysis."""
        pass  # Not used in this view

    def update_analysis_info(self, analysis_data):
        """Updates the analysis information display."""
        pass  # Not used in this view
