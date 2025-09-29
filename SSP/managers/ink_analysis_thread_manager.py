#!/usr/bin/env python3
"""
Ink Analysis Thread Manager - Manages ink analysis operations in a dedicated thread.
"""

import threading
import queue
from PyQt5.QtCore import QObject, pyqtSignal
from managers.ink_analysis_manager import InkAnalysisManager
from database.db_manager import DatabaseManager

class InkAnalysisOperation:
    """Represents an ink analysis operation to be executed."""
    def __init__(self, operation_type, data, callback=None):
        self.operation_type = operation_type
        self.data = data
        self.callback = callback
        self.result = None
        self.error = None

class InkAnalysisThreadManager(QObject):
    """
    Manages ink analysis operations in a dedicated thread with its own database connection.
    """
    
    # Signals
    analysis_completed = pyqtSignal(dict)  # Emits analysis results
    database_updated = pyqtSignal(bool)    # Emits database update success
    
    def __init__(self):
        super().__init__()
        self.operation_queue = queue.Queue()
        self.db_manager = None
        self.ink_analysis_manager = None
        self.thread = None
        self.running = False
        
    def start(self):
        """Start the ink analysis thread."""
        if self.thread is None or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._ink_analysis_worker, daemon=True)
            self.thread.start()
            print("Ink analysis thread manager started")
    
    def stop(self):
        """Stop the ink analysis thread."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        print("Ink analysis thread manager stopped")
    
    def _ink_analysis_worker(self):
        """Worker method that runs in the dedicated ink analysis thread."""
        print(f"Ink analysis worker started in thread: {threading.current_thread().name}")
        
        # Create database manager and ink analysis manager in this thread
        self.db_manager = DatabaseManager()
        self.ink_analysis_manager = InkAnalysisManager(self.db_manager)
        print(f"Database and ink analysis managers created in thread: {threading.current_thread().name}")
        
        while self.running:
            try:
                # Get operation from queue with timeout
                operation = self.operation_queue.get(timeout=0.1)
                
                if operation.operation_type == "analyze_and_update":
                    self._handle_analyze_and_update(operation)
                else:
                    print(f"Unknown operation type: {operation.operation_type}")
                    operation.error = f"Unknown operation type: {operation.operation_type}"
                
                # Call callback if provided
                if operation.callback:
                    operation.callback(operation)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in ink analysis worker: {e}")
                if operation and operation.callback:
                    operation.error = str(e)
                    operation.callback(operation)
    
    def _handle_analyze_and_update(self, operation):
        """Handle analyze and update operation."""
        try:
            pdf_path = operation.data['pdf_path']
            selected_pages = operation.data.get('selected_pages')
            copies = operation.data.get('copies', 1)
            dpi = operation.data.get('dpi', 150)
            color_mode = operation.data.get('color_mode', 'Color')
            
            print(f"DEBUG: Ink analysis thread - Analyzing {pdf_path}")
            print(f"DEBUG: Ink analysis thread - Pages: {selected_pages}, Copies: {copies}, Color Mode: {color_mode}")
            
            # Perform the analysis and update
            result = self.ink_analysis_manager.analyze_and_update_after_print(
                pdf_path=pdf_path,
                selected_pages=selected_pages,
                copies=copies,
                dpi=dpi,
                color_mode=color_mode
            )
            
            operation.result = result
            self.analysis_completed.emit(result)
            
            if result.get('database_updated', False):
                self.database_updated.emit(True)
                print("DEBUG: Ink analysis thread - Database updated successfully")
                # Get updated CMYK levels and emit them
                updated_levels = self.db_manager.get_cmyk_ink_levels()
                if updated_levels:
                    self.analysis_completed.emit({
                        'success': True,
                        'database_updated': True,
                        'cmyk_levels': updated_levels
                    })
            else:
                self.database_updated.emit(False)
                print("DEBUG: Ink analysis thread - Database update failed")
                
        except Exception as e:
            operation.error = str(e)
            print(f"Error in ink analysis: {e}")
            self.database_updated.emit(False)
    
    def analyze_and_update(self, pdf_path, selected_pages=None, copies=1, dpi=150, color_mode="Color", callback=None):
        """Queue an analyze and update operation."""
        operation = InkAnalysisOperation("analyze_and_update", {
            'pdf_path': pdf_path,
            'selected_pages': selected_pages,
            'copies': copies,
            'dpi': dpi,
            'color_mode': color_mode
        }, callback)
        self.operation_queue.put(operation)
        return operation
