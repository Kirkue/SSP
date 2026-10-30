import os
import subprocess
import tempfile
import time
from PyQt5.QtCore import QThread, pyqtSignal
from managers.sms_manager import send_paper_jam_sms, send_printing_error_sms, send_no_paper_sms

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


def parse_printer_alerts(lpstat_output):
    """Return the alert words from `lpstat -l -p <printer>` output (empty when there are none)."""
    for line in lpstat_output.split('\n'):
        line = line.strip()
        if line.startswith("Alerts:"):
            alerts_text = line.replace("Alerts:", "").strip()
            if not alerts_text or alerts_text == "none":
                return []
            return alerts_text.split()
    return []


class PrinterThread(QThread):
    print_success = pyqtSignal(str)  # Emits temp_pdf_path for ink analysis
    print_failed = pyqtSignal(str)
    print_waiting = pyqtSignal()
    paper_empty = pyqtSignal()  # the printer itself says the tray is empty (sent just before print_failed)

    def __init__(self, file_path, copies, color_mode, selected_pages, printer_name):
        super().__init__()
        self.file_path = file_path
        self.copies = copies
        self.color_mode = color_mode
        self.selected_pages = sorted(selected_pages)
        self.printer_name = printer_name
        self.temp_pdf_path = None

    def run(self):
        sim_mode = os.getenv('SIM_MODE', 'false').lower() in ('true', '1', 'yes')

        if not PYMUPDF_AVAILABLE:
            if sim_mode:
                print("[SIM] PyMuPDF unavailable — simulating print job without temp PDF.")
                self._print_succeeded = True
                self.print_success.emit("")
                return
            self.print_failed.emit("PyMuPDF library is not installed.")
            return

        try:
            self.create_temp_pdf_with_selected_pages()
            if not self.temp_pdf_path:
                return

            command = self.build_print_command()

            total_physical_pages = len(self.selected_pages) * self.copies
            print(f"Printing: {len(self.selected_pages)} pages x {self.copies} copies = {total_physical_pages} total pages")
            print(f"Command: {' '.join(command)}")
            print(f"Temp PDF: {self.temp_pdf_path}")

            if not os.path.exists(self.temp_pdf_path):
                raise FileNotFoundError(f"Temporary PDF not found: {self.temp_pdf_path}")

            if sim_mode:
                print(f"[SIM] Skipping CUPS submission. Would run: {' '.join(command)}")
                time.sleep(1)
                self._print_succeeded = True
                self.print_success.emit(self.temp_pdf_path)
                return

            # No timeout — large jobs can take a long time to spool
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )

            if not process.stdout or "request id is" not in process.stdout:
                self.print_failed.emit("Print job was not accepted by CUPS. Check printer connection.")
                return

            job_id = self._extract_job_id(process.stdout)
            if not job_id:
                return

            self.print_waiting.emit()
            if not self.wait_for_print_completion(job_id):
                # The job was reported failed (and the customer refunded), so
                # it must not print later once the fault is cleared.
                self._cancel_cups_job(job_id)
                return

            self._print_succeeded = True
            self.print_success.emit(self.temp_pdf_path)

        except Exception as e:
            self._handle_print_error(f"An unexpected error occurred: {str(e)}")
        finally:
            if not hasattr(self, '_print_succeeded'):
                self.cleanup_temp_pdf()

    def _cancel_cups_job(self, job_id):
        try:
            subprocess.run(['cancel', job_id], capture_output=True, text=True, timeout=10)
            print(f"Cancelled CUPS job {job_id}")
        except Exception as e:
            print(f"Could not cancel CUPS job {job_id}: {e}")

    def _extract_job_id(self, cups_output):
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
            print(f"Error extracting job ID: {e}")
            self.print_failed.emit(f"Error processing CUPS response: {e}")
            return None

    def _handle_print_error(self, error_message):
        print(f"ERROR: {error_message}")
        try:
            send_printing_error_sms(error_message)
        except Exception as sms_error:
            print(f"Failed to send SMS notification: {sms_error}")

        try:
            from utils.error_logger import log_error
            log_error("Printing Error", error_message, "printer_manager")
        except Exception as db_error:
            print(f"Failed to log error to database: {db_error}")

        self.print_failed.emit(error_message)

    def create_temp_pdf_with_selected_pages(self):
        try:
            print(f"Creating temp PDF with pages: {self.selected_pages}")

            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"Source PDF file not found: {self.file_path}")

            original_doc = fitz.open(self.file_path)
            max_page = len(original_doc)

            invalid_pages = [p for p in self.selected_pages if p < 1 or p > max_page]
            if invalid_pages:
                raise ValueError(f"Invalid page numbers: {invalid_pages}")

            pages_0_indexed = [p - 1 for p in self.selected_pages]
            temp_doc = fitz.open()

            for page_num in pages_0_indexed:
                temp_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)

            if len(temp_doc) != len(self.selected_pages):
                raise ValueError(f"Page count mismatch! Expected {len(self.selected_pages)}, got {len(temp_doc)}")

            fd, self.temp_pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="printjob-")
            os.close(fd)

            temp_doc.save(self.temp_pdf_path, garbage=4, deflate=True)
            temp_doc.close()
            original_doc.close()

            if not os.path.exists(self.temp_pdf_path):
                raise Exception("Temp PDF file was not created")

        except Exception as e:
            print(f"Failed to create temporary PDF: {str(e)}")
            self.print_failed.emit(f"Failed to create temporary PDF: {str(e)}")
            self.temp_pdf_path = None

    def wait_for_print_completion(self, job_id):
        min_print_time = 15       # Enforce minimum to avoid false-positive completion at startup
        post_completion_wait = 5  # Buffer period after job disappears from queue
        check_interval = 3
        initial_startup_delay = 5

        elapsed_time = 0
        completion_time = None
        media_empty_sms_sent = False

        time.sleep(initial_startup_delay)
        elapsed_time += initial_startup_delay

        while True:
            try:
                target_printer = self.printer_name
                printer_actively_printing = False

                alerts_result = subprocess.run(
                    ['lpstat', '-l', '-p', target_printer],
                    capture_output=True, text=True
                )

                if alerts_result.returncode == 0:
                    lpstat_out_lower = alerts_result.stdout.lower()
                    if " now printing " in lpstat_out_lower:
                        printer_actively_printing = True

                    alerts_found = parse_printer_alerts(alerts_result.stdout)
                    if alerts_found:
                        if "cups-waiting-for-job-completed" in alerts_found:
                            printer_actively_printing = True

                        if "media-jam-error" in alerts_found or "paper-jam" in alerts_found:
                            self.print_failed.emit(f"Paper jam detected on {target_printer}")
                            try:
                                send_paper_jam_sms()
                            except Exception:
                                pass
                            return False
                        elif "media-empty-error" in alerts_found or "media-needed-error" in alerts_found:
                            self.paper_empty.emit()
                            self.print_failed.emit(f"No paper detected on {target_printer}")
                            try:
                                send_no_paper_sms()
                            except Exception:
                                pass
                            return False
                        elif "media-empty-report" in alerts_found:
                            if not media_empty_sms_sent:
                                try:
                                    send_no_paper_sms()
                                    media_empty_sms_sent = True
                                except Exception:
                                    pass
                            self.paper_empty.emit()
                            self.print_failed.emit(f"No paper detected on {target_printer}")
                            return False
                        elif "paused" in alerts_found:
                            # CUPS sets this when it disables the queue (e.g. after a backend
                            # failure); the job stays queued, so it would never count as complete
                            self.print_failed.emit(f"Printer {target_printer} is paused (CUPS queue disabled)")
                            return False
                        elif "offline" in alerts_found or "stopped" in alerts_found:
                            self.print_failed.emit(f"Printer {target_printer} is offline")
                            return False
                        elif "error" in alerts_found:
                            self.print_failed.emit(f"Printer error on {target_printer}")
                            return False

                cups_job_still_active = self._check_cups_job_status(job_id)

                if not printer_actively_printing and not cups_job_still_active:
                    if elapsed_time < min_print_time:
                        time.sleep(check_interval)
                        elapsed_time += check_interval
                        continue

                    if completion_time is None:
                        completion_time = elapsed_time
                    elif elapsed_time - completion_time >= post_completion_wait:
                        return True
                else:
                    completion_time = None

                time.sleep(check_interval)
                elapsed_time += check_interval

            except Exception as e:
                print(f"Error checking print status: {e}")
                time.sleep(check_interval)
                elapsed_time += check_interval

    def _check_cups_job_status(self, job_id):
        try:
            result = subprocess.run(['lpstat', '-o'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if job_id in line:
                        return True
            return False
        except Exception:
            return True

    def build_print_command(self):
        mode_str = "color" if self.color_mode == "Color" else "monochrome"
        return [
            "lp",
            "-d", self.printer_name,
            "-o", f"print-color-mode={mode_str}",
            "-o", "job-sheets=none",
            "-n", str(self.copies),
            self.temp_pdf_path,
        ]

    def cleanup_temp_pdf(self):
        if self.temp_pdf_path and os.path.exists(self.temp_pdf_path):
            try:
                os.remove(self.temp_pdf_path)
            except OSError as e:
                print(f"Error cleaning up temp file: {e}")
