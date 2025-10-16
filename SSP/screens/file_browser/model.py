import os
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtGui import QPixmap
from config import get_config

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("PyMuPDF not available - PDF preview will be limited")

try:
    from managers.usb_file_manager import USBFileManager
except ImportError:
    class USBFileManager:
        def __init__(self): pass

class PDFAnalysisThread(QThread):
    """Thread for analyzing PDF files in the background."""
    analysis_complete = pyqtSignal(dict, dict)  # pdf_data, analysis_data
    
    def __init__(self, pdf_data):
        super().__init__()
        self.pdf_data = pdf_data
    
    def run(self):
        """Analyzes the PDF file."""
        try:
            if not PYMUPDF_AVAILABLE:
                # Fallback analysis without PyMuPDF
                analysis = {
                    'total_pages': self.pdf_data.get('pages', 1),
                    'black_pages_count': self.pdf_data.get('pages', 1),
                    'color_pages_count': 0,
                    'pricing': {
                        'black_pages_count': self.pdf_data.get('pages', 1),
                        'color_pages_count': 0,
                        'total_cost': 0.0
                    }
                }
                self.analysis_complete.emit(self.pdf_data, analysis)
                return
            
            # Full analysis with PyMuPDF
            doc = fitz.open(self.pdf_data['path'])
            total_pages = len(doc)
            black_pages = 0
            color_pages = 0
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                pixmap = page.get_pixmap()
                img_data = pixmap.tobytes("ppm")
                
                # Simple color detection - check if image has color
                has_color = self._has_color_content(img_data)
                if has_color:
                    color_pages += 1
                else:
                    black_pages += 1
            
            doc.close()
            
            # Calculate pricing using config values
            config = get_config()
            black_rate = config.black_and_white_price
            color_rate = config.color_price
            total_cost = (black_pages * black_rate) + (color_pages * color_rate)
            
            analysis = {
                'total_pages': total_pages,
                'black_pages_count': black_pages,
                'color_pages_count': color_pages,
                'pricing': {
                    'black_pages_count': black_pages,
                    'color_pages_count': color_pages,
                    'total_cost': total_cost
                }
            }
            
            self.analysis_complete.emit(self.pdf_data, analysis)
            
        except Exception as e:
            print(f"Error analyzing PDF: {e}")
            # Fallback analysis on error
            analysis = {
                'total_pages': self.pdf_data.get('pages', 1),
                'black_pages_count': self.pdf_data.get('pages', 1),
                'color_pages_count': 0,
                'pricing': {
                    'black_pages_count': self.pdf_data.get('pages', 1),
                    'color_pages_count': 0,
                    'total_cost': 0.0
                }
            }
            self.analysis_complete.emit(self.pdf_data, analysis)
    
    def _has_color_content(self, img_data):
        """Simple color detection - checks if image has color content."""
        try:
            # Convert to QImage for analysis
            from PyQt5.QtGui import QImage
            img = QImage.fromData(img_data)
            
            # Sample pixels to check for color
            width = img.width()
            height = img.height()
            sample_size = min(100, min(width, height) // 10)
            
            for i in range(0, width, sample_size):
                for j in range(0, height, sample_size):
                    pixel = img.pixel(i, j)
                    r = (pixel >> 16) & 0xFF
                    g = (pixel >> 8) & 0xFF
                    b = pixel & 0xFF
                    
                    # Check if pixel is not grayscale (has color)
                    if abs(r - g) > 10 or abs(g - b) > 10 or abs(r - b) > 10:
                        return True
            
            return False
        except Exception:
            return False

class FileBrowserModel(QObject):
    """Model for the File Browser screen - handles file management and PDF analysis."""
    
    # Signals for UI updates
    files_loaded = pyqtSignal(list)  # list of pdf_data
    pdf_selected = pyqtSignal(dict)  # selected pdf_data
    pdf_analysis_started = pyqtSignal(str)  # filename
    pdf_analysis_completed = pyqtSignal(dict, dict)  # pdf_data, analysis_data
    navigation_requested = pyqtSignal(str)  # screen_name
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self):
        super().__init__()
        self.usb_manager = USBFileManager()
        self.pdf_files = []
        self.selected_pdf = None
        self.analysis_thread = None
        
    def load_pdf_files(self, pdf_files=None):
        """Loads PDF files from USB drive or from provided list."""
        try:
            if pdf_files is not None:
                # PDF files provided from external source (like USB controller)
                self.pdf_files = pdf_files
                print(f"✅ Loaded {len(pdf_files)} PDF files from external source")
            else:
                # No PDF files provided - this is normal when screen is first loaded
                # PDF files will be provided by the USB controller when they are found
                self.pdf_files = []
                print("ℹ️ No PDF files provided - waiting for USB controller to provide files")
            
            self.files_loaded.emit(self.pdf_files)
        except Exception as e:
            self.error_occurred.emit(f"Error loading PDF files: {str(e)}")
    
    def select_pdf(self, pdf_data):
        """Selects a PDF file and starts analysis."""
        self.selected_pdf = pdf_data
        self.pdf_selected.emit(pdf_data)
        
        # Mark file as in use for safety
        if hasattr(self.usb_manager, 'mark_file_in_use'):
            self.usb_manager.mark_file_in_use(pdf_data['path'])
        
        # Start analysis in background thread
        self.pdf_analysis_started.emit(pdf_data['filename'])
        self.analysis_thread = PDFAnalysisThread(pdf_data)
        self.analysis_thread.analysis_complete.connect(self._on_analysis_complete)
        self.analysis_thread.start()
    
    def _on_analysis_complete(self, pdf_data, analysis_data):
        """Handles completion of PDF analysis."""
        # Mark file as complete for safety
        if hasattr(self.usb_manager, 'mark_file_complete'):
            self.usb_manager.mark_file_complete(pdf_data['path'])
        
        self.pdf_analysis_completed.emit(pdf_data, analysis_data)
    
    def go_to_payment(self, pdf_data, analysis_data):
        """Navigates to payment screen with PDF data."""
        config = get_config()
        payment_data = {
            'pdf_data': pdf_data,
            'analysis': analysis_data,
            'selected_pages': list(range(analysis_data['total_pages'])),
            'copies': 1,
            'color_mode': config.default_color_mode,  # Use config default
            'total_cost': analysis_data['pricing']['total_cost']
        }
        self.navigation_requested.emit('payment')
        return payment_data
    
    def go_back_to_usb(self):
        """Navigates back to idle screen."""
        self.navigation_requested.emit('idle')
    
    def cleanup(self):
        """Cleans up resources."""
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.terminate()
            self.analysis_thread.wait(1000)