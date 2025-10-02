"""
Printer Manager Module

Manages print job execution via CUPS (Common Unix Printing System) in background threads.
Handles PDF page selection, print queue monitoring, and error detection (paper jams, 
offline status, etc.).

Key Components:
- PrinterThread: Background thread for executing print jobs
- PrinterManager: Coordinates print jobs and manages printer availability
- Status Monitoring: Active monitoring for paper jams, offline status, and errors

Note: Ink analysis is handled separately by the main application after print completion.
This keeps printing concerns separate from ink consumption tracking.
"""

import os
import subprocess
import tempfile
import threading
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer
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
    Executes print jobs in a background thread to prevent GUI freezing.
    
    Handles the complete print workflow:
    1. Creates temporary PDF with selected pages
    2. Sends print job to CUPS
    3. Monitors print queue and printer status
    4. Cleans up temporary files
    
    Signals:
        print_success(str): Emitted with temp_pdf_path when print completes successfully
        print_failed(str): Emitted with error message when print job fails
        print_waiting: Emitted when job is sent and waiting for completion
    """
    
    print_success = pyqtSignal(str)  # Emits temp_pdf_path for ink analysis
    print_failed = pyqtSignal(str)
    print_waiting = pyqtSignal()

    def __init__(self, file_path, copies, color_mode, selected_pages, printer_name):
        """
        Initialize print thread.
        
        Args:
            file_path: Path to PDF file to print
            copies: Number of copies to print
            color_mode: 'Color' or 'Black and White'
            selected_pages: List of page numbers to print
            printer_name: CUPS printer name
        """
        super().__init__()
        self.file_path = file_path
        self.copies = copies
        self.color_mode = color_mode
        self.selected_pages = sorted(selected_pages)
        self.printer_name = printer_name
        self.temp_pdf_path = None

    def run(self):
        """Execute the complete print workflow."""
        if not PYMUPDF_AVAILABLE:
            self.print_failed.emit("PyMuPDF library is not installed.")
            return

        try:
            # Create temporary PDF with selected pages
            self.create_temp_pdf_with_selected_pages()
            if not self.temp_pdf_path:
                return

            # Build and execute CUPS print command
            command = self.build_print_command()
            config = get_config()
            print(f"Printing: {len(self.selected_pages)} pages, {self.copies} copies, {self.color_mode}")
            
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True,
                timeout=config.printer_timeout
            )

            # Validate print job was accepted by CUPS
            if not process.stdout or "request id is" not in process.stdout:
                self.print_failed.emit("Print job was not accepted by CUPS. Check printer connection.")
                return
            
            # Extract job ID from CUPS response
            job_id = self._extract_job_id(process.stdout)
            if not job_id:
                return
            
            # Wait for print job to complete with active monitoring
            self.print_waiting.emit()
            completion_success = self.wait_for_print_completion(job_id)
            
            if not completion_success:
                return
            
            # Mark as succeeded so temp PDF isn't cleaned up in finally block
            self._print_succeeded = True
            
            # Emit success signal with temp PDF path for ink analysis
            # Main app will clean up temp PDF after ink analysis completes
            self.print_success.emit(self.temp_pdf_path)

        except subprocess.TimeoutExpired:
            self._handle_print_error("Printing command timed out.")
        except FileNotFoundError:
            self._handle_print_error("The 'lp' command was not found. Is CUPS installed?")
        except subprocess.CalledProcessError as e:
            self._handle_print_error(f"CUPS Error: {e.stderr.strip()}")
        except Exception as e:
            self._handle_print_error(f"An unexpected error occurred: {str(e)}")
        finally:
            # Only clean up temp PDF if print failed
            # On success, main app will clean it up after ink analysis
            if not hasattr(self, '_print_succeeded'):
                self.cleanup_temp_pdf()

    def _extract_job_id(self, cups_output):
        """
        Extract job ID from CUPS command output.
        
        Args:
            cups_output: stdout from CUPS lp command
            
        Returns:
            Job ID string or None if extraction fails
        """
        try:
            parts = cups_output.split("request id is")
            if len(parts) > 1:
                job_id_part = parts[1].strip()
                job_id = job_id_part.split()[0].split('(')[0]
                print(f"Print job ID: {job_id}")
                return job_id
            else:
                self.print_failed.emit("Could not extract print job ID from CUPS response.")
                return None
        except Exception as e:
            print(f"❌ Error extracting job ID: {e}")
            self.print_failed.emit(f"Error processing CUPS response: {e}")
            return None

    def _handle_print_error(self, error_message):
        """
        Handle print errors with SMS notification.
        
        Args:
            error_message: Description of the error
        """
        print(f"❌ {error_message}")
        try:
            send_printing_error_sms(error_message)
        except Exception as sms_error:
            print(f"⚠️ Failed to send SMS notification: {sms_error}")
        self.print_failed.emit(error_message)

    def create_temp_pdf_with_selected_pages(self):
        """
        Create a temporary PDF containing only the selected pages.
        
        Uses PyMuPDF to extract pages from the original PDF.
        Sets self.temp_pdf_path to the temporary file path on success.
        """
        try:
            original_doc = fitz.open(self.file_path)
            pages_0_indexed = [p - 1 for p in self.selected_pages]
            
            temp_doc = fitz.open()
            
            # Copy selected pages
            for page_num in pages_0_indexed:
                temp_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)
            
            # Save to temporary file
            fd, self.temp_pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="printjob-")
            os.close(fd)
            temp_doc.save(self.temp_pdf_path, garbage=4, deflate=True)
            temp_doc.close()
            original_doc.close()
            
        except Exception as e:
            print(f"❌ Failed to create temporary PDF: {str(e)}")
            self.print_failed.emit(f"Failed to create temporary PDF: {str(e)}")
            self.temp_pdf_path = None

    def wait_for_print_completion(self, job_id):
        """
        Wait for print job to complete by monitoring printer status.
        
        Simply checks if any printer is actively printing using lpstat -p.
        When no printer shows "now printing", considers the job complete.
        Much simpler and more reliable than tracking individual job IDs.
        
        Args:
            job_id: CUPS job ID (kept for compatibility, but not used)
            
        Returns:
            True if print job completed successfully, False otherwise
        """
        import time
        
        config = get_config()
        max_wait_time = config.printer_timeout * 10
        post_completion_wait = 5  # Wait 5 seconds after completion
        check_interval = 2
        elapsed_time = 0
        completion_time = None
        
        print(f"🖨️ Starting print completion monitoring (timeout: {max_wait_time}s)")
        
        while elapsed_time < max_wait_time:
            try:
                # Check if the specific printer is actively printing
                printer_result = subprocess.run(['lpstat', '-p'], 
                                              capture_output=True, text=True)
                printer_actively_printing = False
                target_printer = "HP_Smart_Tank_580_590_series_5E0E1D_USB"
                
                if printer_result.returncode == 0:
                    for line in printer_result.stdout.split('\n'):
                        line = line.strip()
                        # Look specifically for our target printer with "now printing"
                        if target_printer in line and 'now printing' in line.lower():
                            printer_actively_printing = True
                            print(f"🖨️ Target printer '{target_printer}' still printing: {line}")
                            break
                
                # Check for printer errors (paper jam, offline, etc.)
                printer_status = self._check_printer_status()
                if printer_status['status'] == 'paper_jam':
                    print(f"❌ Paper jam detected: {printer_status['message']}")
                    try:
                        send_paper_jam_sms()
                    except Exception as e:
                        print(f"⚠️ Failed to send SMS: {e}")
                    self.print_failed.emit(f"Paper jam detected: {printer_status['message']}")
                    return False
                elif printer_status['status'] == 'offline':
                    print(f"❌ Printer offline: {printer_status['message']}")
                    self.print_failed.emit(f"Printer offline: {printer_status['message']}")
                    return False
                elif printer_status['status'] == 'error':
                    print(f"❌ Printer error: {printer_status['message']}")
                    self.print_failed.emit(f"Printer error: {printer_status['message']}")
                    return False
                
                # Simple completion logic: no printer actively printing
                if not printer_actively_printing:
                    # No printer is actively printing
                    if completion_time is None:
                        completion_time = elapsed_time
                        print(f"✅ Print job completed after {elapsed_time}s, monitoring for {post_completion_wait}s...")
                    else:
                        # Check if post-completion monitoring is complete
                        time_since_completion = elapsed_time - completion_time
                        if time_since_completion >= post_completion_wait:
                            print(f"✅ Print job successful - no printers actively printing")
                            return True
                else:
                    print(f"⏳ Waiting for printer '{active_printer}' to finish printing...")
                    
                time.sleep(check_interval)
                elapsed_time += check_interval
                    
            except Exception as e:
                print(f"⚠️ Error checking print status: {e}")
                time.sleep(check_interval)
                elapsed_time += check_interval
        
        print(f"❌ Print job timed out after {max_wait_time} seconds")
        return False

    def build_print_command(self):
        """
        Build CUPS lp command for printing.
        
        Returns:
            List of command arguments for subprocess.run()
        """
        mode_str = "color" if self.color_mode == "Color" else "monochrome"
        
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


    def _check_printer_status(self):
        """
        Check current printer status using lpstat.
        
        Improved to handle multiple printers and detect errors across the system.
        
        Returns:
            Dictionary with keys:
                - status: 'ready', 'paper_jam', 'offline', 'error', or 'unknown'
                - message: Human-readable status message
                - details: Additional status details
        """
        try:
            # First check the specific configured printer
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                # If specific printer not found, check all printers for errors
                print(f"⚠️ Configured printer '{self.printer_name}' not found, checking all printers")
                return self._check_all_printers_status()
            
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
    
    def _check_all_printers_status(self):
        """
        Check status across all printers when configured printer is not found.
        
        Returns:
            Dictionary with status information from all printers
        """
        try:
            result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    'status': 'error',
                    'message': 'Failed to get printer status',
                    'details': result.stderr.strip()
                }
            
            output = result.stdout.lower()
            
            # Check for errors across all printers
            if 'jam' in output or 'paper jam' in output:
                return {
                    'status': 'paper_jam',
                    'message': 'Paper jam detected on one or more printers',
                    'details': 'Please clear the paper jam and try again'
                }
            elif 'offline' in output or 'stopped' in output:
                return {
                    'status': 'offline',
                    'message': 'One or more printers are offline or stopped',
                    'details': 'Please check printer connections and power'
                }
            elif 'error' in output:
                return {
                    'status': 'error',
                    'message': 'Printer error detected',
                    'details': output
                }
            else:
                return {
                    'status': 'ready',
                    'message': 'Printers are ready',
                    'details': 'Printers are available for printing'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f"Error checking all printers status: {e}",
                'details': str(e)
            }

    def cleanup_temp_pdf(self):
        """Delete the temporary PDF file if it was created."""
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
            try:
                os.remove(self.temp_pdf_path)
            except OSError as e:
                print(f"⚠️ Error cleaning up temp file: {e}")


class PrinterManager(QObject):
    """
    Manages print jobs and printer availability.
    
    Creates and manages PrinterThread instances for executing print jobs.
    Checks printer availability before starting jobs and forwards signals
    from print threads to the main application.
    
    Signals:
        print_job_successful: Emitted when a print job completes successfully
        print_job_failed(str): Emitted with error message when a print job fails
        print_job_waiting: Emitted when job is sent and waiting for completion
    
    Note:
        After print_job_successful, the temporary PDF is kept alive for ink analysis.
        Call cleanup_last_temp_pdf() after ink analysis completes to remove it.
    """
    
    print_job_successful = pyqtSignal()
    print_job_failed = pyqtSignal(str)
    print_job_waiting = pyqtSignal()

    def __init__(self):
        """Initialize printer manager."""
        super().__init__()
        config = get_config()
        self.printer_name = config.printer_name
        self.print_thread = None
        self.check_printer_availability()

    def print_file(self, file_path, copies, color_mode, selected_pages):
        """
        Initiate a new print job in a background thread.
        
        Args:
            file_path: Path to PDF file to print
            copies: Number of copies to print
            color_mode: 'Color' or 'Black and White'
            selected_pages: List of page numbers to print
        """
        print(f"📄 Print request: {len(selected_pages)} pages × {copies} copies ({color_mode})")
        
        # Prevent duplicate print jobs
        if hasattr(self, 'print_thread') and self.print_thread and self.print_thread.isRunning():
            print("⚠️ Print job already running, ignoring duplicate request")
            return
        
        # Verify printer is available
        if not self.check_printer_availability():
            self.print_job_failed.emit("Printer is not available. Please check printer connection.")
            return
        
        # Verify file exists
        if not os.path.exists(file_path):
            self.print_job_failed.emit(f"File not found: {file_path}")
            return
            
        # Create and start print thread
        self.print_thread = PrinterThread(
            file_path=file_path,
            copies=copies,
            color_mode=color_mode,
            selected_pages=selected_pages,
            printer_name=self.printer_name
        )
        self.print_thread.print_success.connect(self._on_print_success)
        self.print_thread.print_failed.connect(self.print_job_failed.emit)
        self.print_thread.print_waiting.connect(self.print_job_waiting.emit)
        self.print_thread.finished.connect(self.on_thread_finished)
        self.print_thread.start()

    def check_printer_availability(self):
        """
        Check if the configured printer is available and ready.
        
        Verifies:
        - CUPS lp command is available
        - CUPS daemon (cupsd) is running
        - Printer exists in CUPS
        - Printer is not in error state (offline, jammed, etc.)
        
        Returns:
            True if printer is available and ready, False otherwise
        """
        try:
            # Check if lp command exists
            result = subprocess.run(['which', 'lp'], capture_output=True, text=True)
            if result.returncode != 0:
                print("⚠️ 'lp' command not found. Is CUPS installed?")
                return False
            
            # Check if CUPS daemon is running
            try:
                result = subprocess.run(['pgrep', 'cupsd'], capture_output=True, text=True)
                if result.returncode != 0:
                    print("⚠️ CUPS daemon (cupsd) is not running")
                    return False
            except Exception as e:
                print(f"⚠️ Error checking CUPS daemon: {e}")
                return False
                
            # Check if printer exists
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print(f"⚠️ Printer '{self.printer_name}' not found")
                return False
            
            # Check printer state
            output = result.stdout.lower()
            if 'offline' in output or 'stopped' in output or 'jam' in output:
                print(f"⚠️ Printer is in error state")
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ Error checking printer availability: {e}")
            return False

    def check_printer_status(self):
        """
        Get detailed printer status.
        
        Returns:
            Dictionary with status information (see PrinterThread._check_printer_status)
        """
        try:
            result = subprocess.run(['lpstat', '-p', self.printer_name], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                return {
                    'status': 'error',
                    'message': f"Printer '{self.printer_name}' not found or not responding",
                    'details': result.stderr.strip()
                }
            
            output = result.stdout.lower()
            
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
        """
        Check specifically for paper jam condition.
        
        Returns:
            True if paper jam detected, False otherwise
        """
        status = self.check_printer_status()
        return status['status'] == 'paper_jam'

    def _on_print_success(self, temp_pdf_path):
        """
        Handle print success and forward temp PDF path.
        
        Args:
            temp_pdf_path: Path to temporary PDF file (needs to be kept for ink analysis)
        """
        # Store temp PDF path so main app can clean it up after ink analysis
        self.last_temp_pdf_path = temp_pdf_path
        self.print_job_successful.emit()
    
    def cleanup_last_temp_pdf(self):
        """
        Clean up the last temporary PDF file after ink analysis completes.
        
        This should be called by the main app after ink analysis finishes.
        """
        if hasattr(self, 'last_temp_pdf_path') and self.last_temp_pdf_path:
            try:
                import os
                if os.path.exists(self.last_temp_pdf_path):
                    os.remove(self.last_temp_pdf_path)
                    print(f"Cleaned up temp PDF: {self.last_temp_pdf_path}")
                self.last_temp_pdf_path = None
            except Exception as e:
                print(f"⚠️ Error cleaning up temp PDF: {e}")
    
    def on_thread_finished(self):
        """Handle print thread completion."""
        self.print_thread = None
