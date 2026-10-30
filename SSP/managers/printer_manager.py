"""
Printer Manager Module

Coordinates print jobs by spawning PrinterThread instances.
PrinterThread implementation lives in managers/printer_thread.py.
"""

import os
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal
from config import get_config
from managers.printer_thread import PrinterThread


class PrinterManager(QObject):
    """
    Manages print jobs and printer availability.

    Creates PrinterThread instances for executing print jobs in the background.
    Checks printer availability before starting jobs and forwards thread signals
    to the main application.

    After print_job_successful, the temporary PDF is kept alive for ink analysis.
    Call cleanup_last_temp_pdf() after ink analysis completes to remove it.
    """

    print_job_successful = pyqtSignal()
    print_job_failed = pyqtSignal(str)
    print_job_waiting = pyqtSignal()
    paper_empty = pyqtSignal()

    def __init__(self):
        super().__init__()
        config = get_config()
        self.printer_name = config.printer_name
        self.print_thread = None
        self.check_printer_availability()

    def print_file(self, file_path, copies, color_mode, selected_pages):
        print(f"Print request: {len(selected_pages)} pages x {copies} copies ({color_mode})")

        if hasattr(self, 'print_thread') and self.print_thread and self.print_thread.isRunning():
            print("Print job already running, rejecting duplicate request")
            # A paid job dropped silently would neither print nor fail (#59).
            self.print_job_failed.emit("A print job is already running.")
            return

        if not self.check_printer_availability():
            self.print_job_failed.emit("Printer is not available. Please check printer connection.")
            return

        if not os.path.exists(file_path):
            self.print_job_failed.emit(f"File not found: {file_path}")
            return

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
        self.print_thread.paper_empty.connect(self.paper_empty.emit)
        self.print_thread.finished.connect(self.on_thread_finished)
        self.print_thread.start()

    def check_printer_availability(self):
        sim_mode = os.getenv('SIM_MODE', 'false').lower() in ('true', '1', 'yes')
        if sim_mode:
            return True

        try:
            result = subprocess.run(['which', 'lp'], capture_output=True, text=True)
            if result.returncode != 0:
                print("'lp' command not found. Is CUPS installed?")
                return False

            # No pgrep for cupsd: CUPS is socket-activated and cupsd exits when idle,
            # so it's often not running. lpstat below wakes it via cups.sock, and fails
            # if CUPS can't be reached.
            result = subprocess.run(
                ['lpstat', '-p', self.printer_name],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                print(f"Printer '{self.printer_name}' not found")
                return False

            output = result.stdout.lower()
            if 'offline' in output or 'stopped' in output or 'disabled' in output or 'jam' in output:
                print("Printer is in error state")
                return False

            return True

        except Exception as e:
            print(f"Error checking printer availability: {e}")
            return False

    def check_printer_status(self):
        try:
            result = subprocess.run(
                ['lpstat', '-p', self.printer_name],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return {
                    'status': 'error',
                    'message': f"Printer '{self.printer_name}' not found or not responding",
                    'details': result.stderr.strip()
                }
            output = result.stdout.lower()
            if 'jam' in output or 'paper jam' in output:
                return {'status': 'paper_jam', 'message': 'Paper jam detected',
                        'details': 'Please clear the paper jam and try again'}
            elif 'offline' in output or 'stopped' in output:
                return {'status': 'offline', 'message': 'Printer is offline or stopped',
                        'details': 'Please check printer connection and power'}
            elif 'error' in output:
                return {'status': 'error', 'message': 'Printer error detected', 'details': output}
            elif 'idle' in output or 'ready' in output:
                return {'status': 'ready', 'message': 'Printer is ready',
                        'details': 'Printer is available for printing'}
            else:
                return {'status': 'unknown', 'message': 'Unknown printer status', 'details': output}
        except Exception as e:
            return {'status': 'error', 'message': f"Error checking printer status: {e}", 'details': str(e)}

    def check_for_paper_jam(self):
        return self.check_printer_status()['status'] == 'paper_jam'

    def _on_print_success(self, temp_pdf_path):
        self.last_temp_pdf_path = temp_pdf_path
        self.print_job_successful.emit()

    def cleanup_last_temp_pdf(self):
        if hasattr(self, 'last_temp_pdf_path') and self.last_temp_pdf_path:
            try:
                if os.path.exists(self.last_temp_pdf_path):
                    os.remove(self.last_temp_pdf_path)
                    print(f"Cleaned up temp PDF: {self.last_temp_pdf_path}")
                self.last_temp_pdf_path = None
            except Exception as e:
                print(f"Error cleaning up temp PDF: {e}")

    def on_thread_finished(self):
        self.print_thread = None
