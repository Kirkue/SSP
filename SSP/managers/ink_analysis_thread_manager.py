"""
Ink Analysis Thread Manager

Manages ink usage analysis operations in a dedicated thread with its own database connection.
Analyzes printed pages to calculate CMYK ink consumption and updates the database with
new ink levels.

Key Features:
- Thread-safe ink analysis operations
- Independent database connection for thread safety
- Queue-based operation management
- Real-time CMYK level updates via signals
"""

import threading
import queue
from PyQt5.QtCore import QObject, pyqtSignal
from managers.ink_analysis_manager import InkAnalysisManager
from database.db_manager import DatabaseManager


class InkAnalysisOperation:
    """
    Represents an ink analysis operation to be executed.
    
    Attributes:
        operation_type: Type of operation (currently only 'analyze_and_update')
        data: Dictionary containing analysis parameters
        callback: Optional callback function called when operation completes
        result: Operation result dictionary (set after execution)
        error: Error message if operation fails
    """
    
    def __init__(self, operation_type, data, callback=None):
        self.operation_type = operation_type
        self.data = data
        self.callback = callback
        self.result = None
        self.error = None


class InkAnalysisThreadManager(QObject):
    """
    Manages ink analysis operations in a dedicated thread.
    
    Creates its own database connection to avoid SQLite thread safety issues.
    Analyzes PDF pages to calculate ink usage and updates CMYK levels in the database.
    
    Signals:
        analysis_completed(dict): Emits analysis results with keys:
            - success: Boolean indicating if analysis succeeded
            - database_updated: Boolean indicating if database was updated
            - cmyk_levels: Dictionary with updated C, M, Y, K percentages
            - error: Error message if analysis failed
        database_updated(bool): Emits database update success status
    """
    
    analysis_completed = pyqtSignal(dict)
    database_updated = pyqtSignal(bool)
    
    def __init__(self):
        """Initialize the ink analysis thread manager."""
        super().__init__()
        self.operation_queue = queue.Queue()
        self.db_manager = None
        self.ink_analysis_manager = None
        self.thread = None
        self.running = False
        
    def start(self):
        """Start the ink analysis worker thread."""
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._ink_analysis_worker, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop the ink analysis worker thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
    
    def _ink_analysis_worker(self):
        """
        Worker method that runs in the dedicated ink analysis thread.
        
        Creates database and ink analysis managers in this thread for thread safety.
        Processes queued operations sequentially.
        """
        # Create managers in this thread
        self.db_manager = DatabaseManager()
        self.ink_analysis_manager = InkAnalysisManager(self.db_manager)
        
        while self.running:
            try:
                # Get operation from queue with timeout
                operation = self.operation_queue.get(timeout=0.1)
                
                if operation.operation_type == "analyze_and_update":
                    self._handle_analyze_and_update(operation)
                else:
                    operation.error = f"Unknown operation type: {operation.operation_type}"
                
                # Execute callback if provided
                if operation.callback:
                    operation.callback(operation)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error in ink analysis worker: {e}")
                if operation and operation.callback:
                    operation.error = str(e)
                    operation.callback(operation)
    
    def _handle_analyze_and_update(self, operation):
        """
        Handle ink analysis and database update operation.
        
        Args:
            operation: InkAnalysisOperation with PDF path and analysis parameters
        """
        try:
            pdf_path = operation.data['pdf_path']
            selected_pages = operation.data.get('selected_pages')
            copies = operation.data.get('copies', 1)
            dpi = operation.data.get('dpi', 150)
            color_mode = operation.data.get('color_mode', 'Color')
            
            # Perform analysis and update database
            result = self.ink_analysis_manager.analyze_and_update_after_print(
                pdf_path=pdf_path,
                selected_pages=selected_pages,
                copies=copies,
                dpi=dpi,
                color_mode=color_mode
            )
            
            operation.result = result
            self.analysis_completed.emit(result)
            
            # Emit database update status and updated CMYK levels
            if result.get('database_updated', False):
                self.database_updated.emit(True)
                
                # Get and emit updated CMYK levels
                updated_levels = self.db_manager.get_cmyk_ink_levels()
                if updated_levels:
                    self.analysis_completed.emit({
                        'success': True,
                        'database_updated': True,
                        'cmyk_levels': updated_levels
                    })
            else:
                self.database_updated.emit(False)
                
        except Exception as e:
            operation.error = str(e)
            print(f"❌ Error in ink analysis: {e}")
            self.database_updated.emit(False)
    
    def analyze_and_update(self, pdf_path, selected_pages=None, copies=1, dpi=150, color_mode="Color", callback=None):
        """
        Queue an ink analysis and database update operation.
        
        Args:
            pdf_path: Path to PDF file that was printed
            selected_pages: List of page numbers that were printed (None for all pages)
            copies: Number of copies that were printed
            dpi: DPI used for rendering pages during analysis
            color_mode: 'Color' or 'Black and White'
            callback: Optional callback function(operation) called when complete
            
        Returns:
            InkAnalysisOperation object
        """
        operation = InkAnalysisOperation("analyze_and_update", {
            'pdf_path': pdf_path,
            'selected_pages': selected_pages,
            'copies': copies,
            'dpi': dpi,
            'color_mode': color_mode
        }, callback)
        self.operation_queue.put(operation)
        return operation
