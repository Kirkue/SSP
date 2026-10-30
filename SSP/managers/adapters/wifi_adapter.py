# managers/adapters/wifi_adapter.py
#
# Validates files coming through the Wi-Fi captive-portal upload (magic
# bytes + MIME per project_objectives.txt #5) and hands accepted ones to
# SessionManager. Deliberately has no FastAPI import: webapp/routers/upload.py
# is the only layer that knows about HTTP, so this class takes plain bytes
# in and returns a plain result, testable the same way as
# PaymentAlgorithmManager (construct with a fake collaborator, call methods).
#
# handle_upload() takes a whole batch of files (the web UI lets a user stage
# several before confirming) and validates all-or-nothing: if any file in
# the batch fails validation, the whole batch is rejected and nothing is
# written to disk. The user already reviewed the staged list client-side
# before confirming, so a partial success would be confusing to reconcile
# against the single OTP/QR result page.
#
# Past the cheap checks (MIME, size, %PDF header), each file is also opened with
# managers.pdf_check.check_pdf, the same check the file browser applies, so the
# customer hears about a damaged, empty or password-protected PDF on their phone
# instead of at the kiosk. That needs a file on disk, so files are written first and
# the whole batch is deleted again if any of them fails.

import os
import uuid
from typing import BinaryIO, List, Optional, Tuple

from managers.pdf_check import check_pdf
from managers.session_manager import Session

PDF_MAGIC = b"%PDF"
PDF_MIME_TYPES = {"application/pdf"}
MAX_FILES_PER_UPLOAD = 20  # fixed cap on files per batch, not operator-configurable


class WifiAdapter:
    def __init__(self, session_manager, upload_dir: str, max_size_bytes: int):
        self.session_manager = session_manager
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes
        os.makedirs(self.upload_dir, exist_ok=True)

    def _validate_one(
        self, file_obj: BinaryIO, filename: str, content_type: str
    ) -> Tuple[Optional[str], Optional[bytes]]:
        """Returns (error_message, data) — exactly one of the two is not None."""
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        if mime not in PDF_MIME_TYPES:
            return f"'{filename}': unsupported content type: {content_type}", None

        data = file_obj.read(self.max_size_bytes + 1)
        if len(data) > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            return f"'{filename}': exceeds the {max_mb:.0f}MB limit", None
        if not data:
            return f"'{filename}': empty file", None
        if not data.startswith(PDF_MAGIC):
            return f"'{filename}': not a valid PDF (missing %PDF header)", None

        return None, data

    def handle_upload(
        self,
        uploads: List[Tuple[BinaryIO, str, str]],
        metadata: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Session]]:
        """
        Validate a batch of uploaded files and, on success, register them
        as one session with SessionManager. uploads is a list of
        (file_obj, filename, content_type) tuples. Returns
        (success, message, session).
        """
        if not uploads:
            return False, "No files were selected", None
        if len(uploads) > MAX_FILES_PER_UPLOAD:
            return False, f"Too many files (max {MAX_FILES_PER_UPLOAD})", None

        validated = []  # list of (filename, data)
        for file_obj, filename, content_type in uploads:
            error, data = self._validate_one(file_obj, filename, content_type)
            if error:
                return False, error, None
            validated.append((filename, data))

        # Only write to disk once every file in the batch has passed the cheap
        # validation. check_pdf needs a real file, so a file that fails it removes
        # everything written so far, keeping the all-or-nothing contract.
        saved_files = []
        for filename, data in validated:
            # Filename is stored as metadata only, never used to build a
            # path — the on-disk name is always a fresh UUID so a malicious
            # filename (e.g. "../../etc/passwd") can't escape upload_dir.
            dest_path = os.path.join(self.upload_dir, f"{uuid.uuid4().hex}.pdf")
            with open(dest_path, "wb") as f:
                f.write(data)
            saved_files.append({"path": dest_path, "original_filename": filename})

            _, pdf_error = check_pdf(dest_path)
            if pdf_error:
                for saved in saved_files:
                    try:
                        os.remove(saved["path"])
                    except OSError:
                        pass
                return False, f"'{filename}': {pdf_error}", None

        session = self.session_manager.create_session(
            source="wifi",
            files=saved_files,
            metadata=metadata,
        )
        return True, "Upload accepted", session
