# printing/printer_manager.py
import os
import subprocess
import tempfile
import threading
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from config import get_config
from managers.ink_analysis_manager import InkAnalysisManager
from managers.sms_manager import send_paper_jam_sms, send_printing_error_sms

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
            print(f"DEBUG: About to execute CUPS command: {' '.join(command)}")
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True,  # Raises CalledProcessError on non-zero exit codes
                timeout=config.printer_timeout  # Use config timeout
            )
            
            print(f"DEBUG: CUPS command executed successfully")
            print(f"DEBUG: CUPS stdout: {process.stdout}")
            print(f"DEBUG: CUPS stderr: {process.stderr}")

            # Step 4: Validate the print job was actually sent
            print(f"Print job sent to CUPS successfully. stdout: {process.stdout}")
            
            # Check if the print job was actually accepted by CUPS
            if not process.stdout or "request id is" not in process.stdout:
                print("ERROR: CUPS did not return a job ID - print job may have failed")
                self.print_failed.emit("Print job was not accepted by CUPS. Check printer connection.")
                return
            
            # Extract job ID from the output (format: "request id is HP_Smart_Tank_580_590_series_5E0E1D_USB-1 (1 file(s))")
            job_id = None
            print(f"DEBUG: Full CUPS output: '{process.stdout}'")
            if "request id is" in process.stdout:
                try:
                    # More robust job ID extraction
                    parts = process.stdout.split("request id is")
                    if len(parts) > 1:
                        job_id_part = parts[1].strip()
                        # Extract the job ID (everything before the first space or parenthesis)
                        job_id = job_id_part.split()[0].split('(')[0]
                        print(f"Print job ID extracted: '{job_id}'")
                    else:
                        print("Could not find job ID in output")
                        self.print_failed.emit("Could not extract print job ID from CUPS response.")
                        return
                except Exception as e:
                    print(f"Error extracting job ID: {e}")
                    self.print_failed.emit(f"Error processing CUPS response: {e}")
                    return
            else:
                print("No 'request id is' found in CUPS output")
                self.print_failed.emit("CUPS did not return a valid job ID.")
                return
            
            # Wait for the print job to actually complete
            if job_id:
                # Signal that we're now waiting for actual printing to complete
                self.print_waiting.emit()
                print(f"DEBUG: Starting to wait for print job {job_id} to complete...")
                completion_success = self.wait_for_print_completion(job_id)
                if not completion_success:
                    print("WARNING: Print job completion check failed, but continuing...")
            else:
                # If we can't get job ID, wait a reasonable time for printing
                print("WARNING: No job ID available, waiting 60 seconds for print job to complete...")
                self.print_waiting.emit()
                import time
                time.sleep(60)  # Increased from 30 to 60 seconds
            
            # Step 5: Analyze ink usage and update database
            print("DEBUG: About to start ink analysis...")
            try:
                self._analyze_and_update_ink_usage()
                print("DEBUG: Ink analysis operation queued, waiting for completion...")
                # Don't emit print_success here - wait for ink analysis callback
            except Exception as e:
                print(f"DEBUG: Ink analysis failed: {e}")
                print("DEBUG: Continuing despite ink analysis failure...")
                # Only emit success if we actually completed a print job
                if job_id or completion_success:
                    print("DEBUG: Emitting print_success signal - print job was completed")
                    self.print_success.emit()
                    print("DEBUG: print_success signal emitted")
                else:
                    print("DEBUG: No print job was actually completed, not emitting success")

        except subprocess.TimeoutExpired:
            error_message = "Printing command timed out."
            print(f"Printing error - sending SMS notification: {error_message}")
            try:
                send_printing_error_sms(error_message)
                print("SMS notification sent for printing timeout")
            except Exception as sms_error:
                print(f"Failed to send SMS notification: {sms_error}")
            self.print_failed.emit(error_message)
        except FileNotFoundError:
            error_message = "The 'lp' command was not found. Is CUPS installed?"
            print(f"Printing error - sending SMS notification: {error_message}")
            try:
                send_printing_error_sms(error_message)
                print("SMS notification sent for missing lp command")
            except Exception as sms_error:
                print(f"Failed to send SMS notification: {sms_error}")
            self.print_failed.emit(error_message)
        except subprocess.CalledProcessError as e:
            error_message = f"CUPS Error: {e.stderr.strip()}"
            print(f"Printing error - sending SMS notification: {error_message}")
            try:
                send_printing_error_sms(error_message)
                print("SMS notification sent for CUPS error")
            except Exception as sms_error:
                print(f"Failed to send SMS notification: {sms_error}")
            print(error_message)
            self.print_failed.emit(error_message)
        except Exception as e:
            error_message = f"An unexpected error occurred: {str(e)}"
            print(f"Printing error - sending SMS notification: {error_message}")
            try:
                send_printing_error_sms(error_message)
                print("SMS notification sent for unexpected error")
            except Exception as sms_error:
                print(f"Failed to send SMS notification: {sms_error}")
            self.print_failed.emit(error_message)
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
        """Wait for the print job to actually complete with simplified monitoring."""
        import time
        
        print(f"Waiting for print job {job_id} to complete...")
        config = get_config()
        max_wait_time = config.printer_timeout * 10  # 10x timeout for completion wait
        check_interval = 5   # Check every 5 seconds (back to original)
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
                    # Job still in queue, check for critical errors only
                    print(f"Print job {job_id} still printing... ({elapsed_time}s elapsed)")
                    
                    # Only check for critical errors that would stop printing
                    try:
                        printer_status = self._check_printer_status()
                        if printer_status['status'] == 'paper_jam':
                            print(f"Paper jam detected during printing: {printer_status['message']}")
                            
                            # Send SMS notification for paper jam
                            print("Paper jam detected during printing - sending SMS notification")
                            try:
                                send_paper_jam_sms()
                                print("SMS notification sent for paper jam during printing")
                            except Exception as e:
                                print(f"Failed to send SMS notification: {e}")
                            
                            self.print_failed.emit(f"Paper jam detected: {printer_status['message']}")
                            return False
                        elif printer_status['status'] == 'offline':
                            print(f"Printer went offline during printing: {printer_status['message']}")
                            self.print_failed.emit(f"Printer offline: {printer_status['message']}")
                            return False
                    except Exception as e:
                        print(f"Error checking printer status during printing: {e}")
                        # Don't fail the print job for status check errors
                    
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
                color_mode=self.color_mode,  # Pass color mode to ink analysis
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
        
        # Emit print_success signal now that ink analysis is complete
        print("DEBUG: Ink analysis completed, emitting print_success signal...")
        print("DEBUG: Current thread for signal emission:", threading.current_thread().name)
        
        try:
            # Use QTimer.singleShot to emit signal from main thread
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self.print_success.emit)
            print("DEBUG: print_success signal queued for main thread emission")
            print("DEBUG: Signal emission completed successfully")
        except Exception as e:
            print(f"DEBUG: ERROR emitting print_success signal: {e}")
            import traceback
            traceback.print_exc()
        
        print("DEBUG: Ink analysis callback method completed")

    def _check_printer_status(self):
        """Check printer status for errors including paper jams."""
        try:
            # Get detailed printer status
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    'status': 'error',
                    'message': f"Printer '{self.printer_name}' not found or not responding",
                    'details': result.stderr.strip()
                }
            
            output = result.stdout.lower()
            
            # Check for various error conditions
            if 'jam' in output or 'paper jam' in output:
                return {
                    'status': 'paper_jam',
                    'message': 'Paper jam detected',
                    'details': 'Please clear the paper jam and try again'
                }
            elif 'offline' in output or 'stopped' in output:
                return {
                    'status': 'offline',
                    'message': 'Printer is offline or stopped',
                    'details': 'Please check printer connection and power'
                }
            elif 'error' in output:
                return {
                    'status': 'error',
                    'message': 'Printer error detected',
                    'details': output
                }
            elif 'idle' in output or 'ready' in output:
                return {
                    'status': 'ready',
                    'message': 'Printer is ready',
                    'details': 'Printer is available for printing'
                }
            else:
                return {
                    'status': 'unknown',
                    'message': 'Unknown printer status',
                    'details': output
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Error checking printer status: {e}",
                'details': str(e)
            }

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

    def __init__(self, ink_analysis_thread_manager=None):
        super().__init__()
        config = get_config()
        self.printer_name = config.printer_name
        self.print_thread = None
        self.ink_analysis_thread_manager = ink_analysis_thread_manager
        self.check_printer_availability()

    def print_file(self, file_path, copies, color_mode, selected_pages):
        """
        Initiates a new print job in a background thread.
        """
        print(f"Received print request for {file_path}")
        print(f"Printer name: {self.printer_name}")
        print(f"Copies: {copies}, Color mode: {color_mode}, Pages: {selected_pages}")
        
        # Check if a print job is already running
        if hasattr(self, 'print_thread') and self.print_thread and self.print_thread.isRunning():
            print("WARNING: Print job already running, ignoring duplicate request")
            return
        
        # Check printer availability (basic check only)
        if not self.check_printer_availability():
            self.print_job_failed.emit("Printer is not available. Please check printer connection.")
            return
        
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
            ink_analysis_thread_manager=self.ink_analysis_thread_manager
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

    def check_printer_status(self):
        """Check printer status for errors including paper jams."""
        try:
            # Get detailed printer status
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    'status': 'error',
                    'message': f"Printer '{self.printer_name}' not found or not responding",
                    'details': result.stderr.strip()
                }
            
            output = result.stdout.lower()
            
            # Check for various error conditions
            if 'jam' in output or 'paper jam' in output:
                return {
                    'status': 'paper_jam',
                    'message': 'Paper jam detected',
                    'details': 'Please clear the paper jam and try again'
                }
            elif 'offline' in output or 'stopped' in output:
                return {
                    'status': 'offline',
                    'message': 'Printer is offline or stopped',
                    'details': 'Please check printer connection and power'
                }
            elif 'error' in output:
                return {
                    'status': 'error',
                    'message': 'Printer error detected',
                    'details': output
                }
            elif 'idle' in output or 'ready' in output:
                return {
                    'status': 'ready',
                    'message': 'Printer is ready',
                    'details': 'Printer is available for printing'
                }
            else:
                return {
                    'status': 'unknown',
                    'message': 'Unknown printer status',
                    'details': output
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Error checking printer status: {e}",
                'details': str(e)
            }

    def check_for_paper_jam(self):
        """Specifically check for paper jam condition."""
        status = self.check_printer_status()
        return status['status'] == 'paper_jam'

    def on_thread_finished(self):
        print("Print thread has finished.")
        self.print_thread = None