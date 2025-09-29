# printing/printer_manager.py
import os
import subprocess
import tempfile
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from config import get_config
from managers.ink_analysis_manager import InkAnalysisManager

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

class PrinterThread(QThread):
    """
    Handles the actual printing task in a background thread to avoid freezing the GUI.
    """
    print_success = pyqtSignal()
    print_failed = pyqtSignal(str)
    print_waiting = pyqtSignal()

    def __init__(self, file_path, copies, color_mode, selected_pages, printer_name, ink_analysis_thread_manager=None):
        super().__init__()
        self.file_path = file_path
        self.copies = copies
        self.color_mode = color_mode
        self.selected_pages = sorted(selected_pages)
        self.printer_name = printer_name
        self.temp_pdf_path = None
        self.ink_analysis_thread_manager = ink_analysis_thread_manager
        
        if ink_analysis_thread_manager:
            print("DEBUG: Ink analysis thread manager provided")
        else:
            print("DEBUG: No ink analysis thread manager provided, skipping ink analysis setup")

    def run(self):
        """The main logic for the printing thread."""
        if not PYMUPDF_AVAILABLE:
            self.print_failed.emit("PyMuPDF library is not installed.")
            return

        try:
            # Step 1: Create a temporary PDF with only the selected pages
            self.create_temp_pdf_with_selected_pages()
            if not self.temp_pdf_path:
                return # Error already emitted inside the creation method

            # Step 2: Construct the CUPS lp command
            command = self.build_print_command()
            mode_str = "color" if self.color_mode == "Color" else "monochrome"
            config = get_config()
            print(f"Executing print command: {' '.join(command)}")
            print(f"Printing file: {self.temp_pdf_path}")
            print(f"Printer: {self.printer_name}")
            print(f"Color mode: {self.color_mode} -> {mode_str}")
            print(f"Copies: {self.copies}")

            # Step 3: Execute the command and wait for it to complete
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True,  # Raises CalledProcessError on non-zero exit codes
                timeout=config.printer_timeout  # Use config timeout
            )

            # Step 4: Check the result and wait for print job completion
            print(f"Print job sent to CUPS successfully. stdout: {process.stdout}")
            
            # Extract job ID from the output (format: "request id is HP_Smart_Tank_580_590_series_5E0E1D_USB-1 (1 file(s))")
            job_id = None
            if "request id is" in process.stdout:
                try:
                    job_id = process.stdout.split("request id is")[1].split()[0]
                    print(f"Print job ID: {job_id}")
                except:
                    print("Could not extract job ID from output")
            
            # Wait for the print job to actually complete
            if job_id:
                # Signal that we're now waiting for actual printing to complete
                self.print_waiting.emit()
                self.wait_for_print_completion(job_id)
            else:
                # If we can't get job ID, wait a reasonable time for printing
                print("Waiting 30 seconds for print job to complete...")
                self.print_waiting.emit()
                import time
                time.sleep(30)
            
            # Step 5: Analyze ink usage and update database
            print("DEBUG: About to start ink analysis...")
            self._analyze_and_update_ink_usage()
            print("DEBUG: Ink analysis completed")
            
            self.print_success.emit()

        except subprocess.TimeoutExpired:
            self.print_failed.emit("Printing command timed out.")
        except FileNotFoundError:
            self.print_failed.emit("The 'lp' command was not found. Is CUPS installed?")
        except subprocess.CalledProcessError as e:
            error_message = f"CUPS Error: {e.stderr.strip()}"
            print(error_message)
            self.print_failed.emit(error_message)
        except Exception as e:
            self.print_failed.emit(f"An unexpected error occurred: {str(e)}")
        finally:
            # Step 5: Clean up the temporary file
            self.cleanup_temp_pdf()

    def create_temp_pdf_with_selected_pages(self):
        """
        Creates a new PDF file containing only the pages the user selected.
        """
        try:
            original_doc = fitz.open(self.file_path)
            # fitz requires a 0-indexed list of pages
            pages_0_indexed = [p - 1 for p in self.selected_pages]
            
            temp_doc = fitz.open()  # Create a new empty PDF
            
            # Copy each selected page individually (compatible with older PyMuPDF versions)
            for page_num in pages_0_indexed:
                temp_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)
            
            # Save to a temporary file
            fd, self.temp_pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="printjob-")
            os.close(fd)
            temp_doc.save(self.temp_pdf_path, garbage=4, deflate=True)
            temp_doc.close()
            original_doc.close()
            print(f"Created temporary PDF for printing at: {self.temp_pdf_path}")
        except Exception as e:
            error_msg = f"Failed to create temporary PDF: {str(e)}"
            print(error_msg)
            self.print_failed.emit(error_msg)
            self.temp_pdf_path = None

    def wait_for_print_completion(self, job_id):
        """Wait for the print job to actually complete."""
        import time
        
        print(f"Waiting for print job {job_id} to complete...")
        config = get_config()
        max_wait_time = config.printer_timeout * 10  # 10x timeout for completion wait
        check_interval = 5   # Check every 5 seconds
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                # Check if the job is still in the queue
                result = subprocess.run(['lpstat', '-o', job_id], 
                                      capture_output=True, text=True)
                
                print(f"lpstat result for {job_id}: returncode={result.returncode}, stdout='{result.stdout.strip()}'")
                
                if result.returncode != 0 or not result.stdout.strip():
                    # Job is no longer in the queue, it's completed
                    print(f"Print job {job_id} completed after {elapsed_time} seconds")
                    return True
                else:
                    print(f"Print job {job_id} still printing... ({elapsed_time}s elapsed)")
                    time.sleep(check_interval)
                    elapsed_time += check_interval
                    
            except Exception as e:
                print(f"Error checking print job status: {e}")
                time.sleep(check_interval)
                elapsed_time += check_interval
        
        print(f"Print job {job_id} timed out after {max_wait_time} seconds")
        return False

    def build_print_command(self):
        """Constructs the list of arguments for the subprocess call."""
        mode_str = "color" if self.color_mode == "Color" else "monochrome"
        
        # Use the exact command format specified for Raspberry Pi
        command = [
            "lp",
            "-d", self.printer_name,
            "-o", f"print-color-mode={mode_str}",
            self.temp_pdf_path
        ]
        
        # Add copies if more than 1
        if self.copies > 1:
            command.insert(-1, "-n")
            command.insert(-1, str(self.copies))
        
        return command

    def _analyze_and_update_ink_usage(self):
        """Analyze ink usage and update database after successful printing."""
        print("DEBUG: _analyze_and_update_ink_usage called")
        if not self.ink_analysis_thread_manager:
            print("Warning: No ink analysis thread manager available, skipping ink analysis")
            return
        
        try:
            print("Starting ink usage analysis after printing...")
            print(f"DEBUG: PDF path: {self.file_path}")
            print(f"DEBUG: Selected pages: {self.selected_pages}")
            print(f"DEBUG: Copies: {self.copies}")
            
            # Queue the analysis operation in the dedicated thread
            operation = self.ink_analysis_thread_manager.analyze_and_update(
                pdf_path=self.file_path,
                selected_pages=self.selected_pages,
                copies=self.copies,
                dpi=150,
                callback=self._on_ink_analysis_completed
            )
            
            print("DEBUG: Ink analysis operation queued in dedicated thread")
                
        except Exception as e:
            print(f"Error during ink analysis: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the print job if ink analysis fails
            pass
    
    def _on_ink_analysis_completed(self, operation):
        """Callback for when ink analysis is completed."""
        if operation.error:
            print(f"Ink analysis failed: {operation.error}")
        else:
            result = operation.result
            if result.get('success', False):
                print("Ink analysis completed successfully")
                if result.get('database_updated', False):
                    print("Database updated with new ink levels")
                else:
                    print("Warning: Database update failed")
            else:
                print(f"Ink analysis failed: {result.get('error', 'Unknown error')}")

    def cleanup_temp_pdf(self):
        """Deletes the temporary PDF file if it was created."""
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
            try:
                os.remove(self.temp_pdf_path)
                print(f"Cleaned up temporary file: {self.temp_pdf_path}")
            except OSError as e:
                print(f"Error cleaning up temp file {self.temp_pdf_path}: {e}")

class PrinterManager(QObject):
    """
    Manages print jobs by spawning PrinterThread instances.
    """
    print_job_successful = pyqtSignal()
    print_job_failed = pyqtSignal(str)
    print_job_waiting = pyqtSignal()

    def __init__(self, db_manager=None):
        super().__init__()
        config = get_config()
        self.printer_name = config.printer_name
        self.print_thread = None
        self.db_manager = db_manager
        self.check_printer_availability()

    def print_file(self, file_path, copies, color_mode, selected_pages):
        """
        Initiates a new print job in a background thread.
        """
        print(f"Received print request for {file_path}")
        print(f"Printer name: {self.printer_name}")
        print(f"Copies: {copies}, Color mode: {color_mode}, Pages: {selected_pages}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            self.print_job_failed.emit(f"File not found: {file_path}")
            return
            
        self.print_thread = PrinterThread(
            file_path=file_path,
            copies=copies,
            color_mode=color_mode,
            selected_pages=selected_pages,
            printer_name=self.printer_name,
            db_manager=self.db_manager
        )
        self.print_thread.print_success.connect(self.print_job_successful.emit)
        self.print_thread.print_failed.connect(self.print_job_failed.emit)
        self.print_thread.print_waiting.connect(self.print_job_waiting.emit)
        self.print_thread.finished.connect(self.on_thread_finished)
        self.print_thread.start()

    def check_printer_availability(self):
        """Check if the configured printer is available."""
        try:
            # Check if lp command is available
            result = subprocess.run(['which', 'lp'], capture_output=True, text=True)
            if result.returncode != 0:
                print("WARNING: 'lp' command not found. CUPS may not be installed.")
                return False
                
            # Check if printer exists
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                print(f"WARNING: Printer '{self.printer_name}' not found.")
                print("Available printers:")
                subprocess.run(['lpstat', '-p'], capture_output=False)
                return False
                
            print(f"Printer '{self.printer_name}' is available.")
            return True
            
        except Exception as e:
            print(f"Error checking printer availability: {e}")
            return False

    def on_thread_finished(self):
        print("Print thread has finished.")
        self.print_thread = None