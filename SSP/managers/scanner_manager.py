# managers/scanner_manager.py
#
# Orchestrates one scan session (start -> scan_page* -> [rescan_last] ->
# finish/cancel) on top of a ScannerInterface. Pure Python, no PyQt import —
# directly unit-testable with SimScanner the same way PaymentAlgorithmManager
# is tested against a fake DatabaseManager. The async wrapper that runs these
# calls off the main thread lives in managers/scanner_thread.py.

import os
import shutil
import tempfile
import time

import fitz  # PyMuPDF

from managers.scan_progress import ScanTimeEstimator
from managers.scanner import ScannerError, ScannerInterface, build_scanner_from_config


class ScannerManager:
    def __init__(self, scanner: ScannerInterface = None, dpi: int = None):
        if scanner is None:
            scanner = build_scanner_from_config()
        if dpi is None:
            from config import get_config
            dpi = get_config().scanner_dpi

        self.scanner = scanner
        self.dpi = dpi
        self.colour = False   # per session, set by the screen; greyscale scans are ~2x faster
        self.timings = ScanTimeEstimator()
        self.session_dir = None
        self.pages = []  # ordered list of page image paths

    def expected_scan_seconds(self) -> float:
        """How long the next page should take, from recent scans of the same kind."""
        return self.timings.expected(self.colour)

    def start_session(self):
        """Begin a fresh scan session, discarding any stale one."""
        self.cancel()
        self.session_dir = tempfile.mkdtemp(prefix="scan-session-")

    def scan_page(self) -> dict:
        """Scan one page and append it to the session. Returns
        {'page_number': int, 'path': str}."""
        if self.session_dir is None:
            self.start_session()

        started = time.monotonic()
        path = self.scanner.scan_page(self.dpi, self.colour)
        self.timings.record(self.colour, time.monotonic() - started)
        self.pages.append(path)
        return {"page_number": len(self.pages), "path": path}

    def rescan_last(self) -> dict:
        """Discard the last page and scan a replacement in its place."""
        if not self.pages:
            raise ScannerError("No page to rescan — scan at least one page first.")

        stale_path = self.pages.pop()
        self._delete(stale_path)
        return self.scan_page()

    def page_count(self) -> int:
        return len(self.pages)

    def cancel(self):
        """Discard the current session's pages and temp directory."""
        for path in self.pages:
            self._delete(path)
        self.pages = []

        if self.session_dir and os.path.isdir(self.session_dir):
            shutil.rmtree(self.session_dir, ignore_errors=True)
        self.session_dir = None

    def finish(self) -> dict:
        """Combine the session's pages into one PDF. Returns
        {'pdf_path': str, 'page_count': int}."""
        if not self.pages:
            raise ScannerError("No pages scanned — nothing to combine into a PDF.")
        if self.session_dir is None:
            self.session_dir = tempfile.mkdtemp(prefix="scan-session-")

        page_count = len(self.pages)
        combined = fitz.open()
        for image_path in self.pages:
            image_doc = fitz.open(image_path)
            page_pdf = fitz.open("pdf", image_doc.convert_to_pdf())
            combined.insert_pdf(page_pdf)
            image_doc.close()
            page_pdf.close()

        fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix="scan-", dir=self.session_dir)
        os.close(fd)
        combined.save(pdf_path)
        combined.close()

        for image_path in self.pages:
            self._delete(image_path)
        self.pages = []

        return {"pdf_path": pdf_path, "page_count": page_count}

    @staticmethod
    def _delete(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
