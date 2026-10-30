"""
Tests for WifiAdapter — pure logic, no FastAPI/HTTP involved. Wired to a
real SessionManager backed by the same in-memory FakeDBManager used in
test_session_manager.py, so these exercise the full validate -> save ->
create_session path without touching sqlite or a running server.
"""
import io
import os

import fitz

from managers.adapters.wifi_adapter import WifiAdapter, MAX_FILES_PER_UPLOAD
from managers.session_manager import SessionManager
from tests.test_session_manager import FakeDBManager

def _real_pdf(pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


PDF_BYTES = _real_pdf()


def _make_adapter(tmp_path, max_size_bytes=1024 * 1024):
    db = FakeDBManager()
    session_manager = SessionManager(db)
    upload_dir = str(tmp_path / "uploads")
    adapter = WifiAdapter(session_manager, upload_dir, max_size_bytes)
    return adapter, db, upload_dir


class TestHandleUpload:
    def test_accepts_valid_pdf(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "document.pdf", "application/pdf")]
        )
        assert success is True
        assert session is not None
        assert len(session.files) == 1
        assert os.path.dirname(session.files[0]['path']) == upload_dir
        with open(session.files[0]['path'], "rb") as f:
            assert f.read() == PDF_BYTES

    def test_accepts_content_type_with_charset_param(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "document.pdf", "application/pdf; charset=binary")]
        )
        assert success is True

    def test_rejects_wrong_mime_type(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "document.png", "image/png")]
        )
        assert success is False
        assert session is None
        assert os.listdir(upload_dir) == [] if os.path.isdir(upload_dir) else True

    def test_rejects_missing_pdf_magic_bytes(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(b"not actually a pdf"), "document.pdf", "application/pdf")]
        )
        assert success is False
        assert "PDF" in message

    def test_rejects_empty_file(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(b""), "document.pdf", "application/pdf")]
        )
        assert success is False

    def test_rejects_oversized_file(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path, max_size_bytes=10)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "document.pdf", "application/pdf")]
        )
        assert success is False
        assert "limit" in message.lower()

    def test_malicious_filename_does_not_escape_upload_dir(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "../../etc/passwd", "application/pdf")]
        )
        assert success is True
        assert os.path.dirname(session.files[0]['path']) == upload_dir
        assert os.path.commonpath([upload_dir, session.files[0]['path']]) == upload_dir

    def test_metadata_passed_through_to_session(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(PDF_BYTES), "document.pdf", "application/pdf")],
            metadata="note: rush order",
        )
        assert success is True
        assert db.sessions[session.session_id]['metadata'] == "note: rush order"

    def test_creates_upload_dir_if_missing(self, tmp_path):
        upload_dir = str(tmp_path / "nested" / "uploads")
        db = FakeDBManager()
        WifiAdapter(SessionManager(db), upload_dir, 1024 * 1024)
        assert os.path.isdir(upload_dir)

    def test_accepts_multiple_valid_pdfs(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload([
            (io.BytesIO(PDF_BYTES), "a.pdf", "application/pdf"),
            (io.BytesIO(PDF_BYTES), "b.pdf", "application/pdf"),
            (io.BytesIO(PDF_BYTES), "c.pdf", "application/pdf"),
        ])
        assert success is True
        assert len(session.files) == 3
        names = {f['original_filename'] for f in session.files}
        assert names == {"a.pdf", "b.pdf", "c.pdf"}
        for f in session.files:
            with open(f['path'], "rb") as fh:
                assert fh.read() == PDF_BYTES

    def test_rejects_whole_batch_if_one_file_invalid(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload([
            (io.BytesIO(PDF_BYTES), "a.pdf", "application/pdf"),
            (io.BytesIO(b"not a pdf"), "bad.pdf", "application/pdf"),
            (io.BytesIO(PDF_BYTES), "c.pdf", "application/pdf"),
        ])
        assert success is False
        assert session is None
        assert "bad.pdf" in message
        # All-or-nothing: nothing from the batch should have been written to disk
        assert os.listdir(upload_dir) == [] if os.path.isdir(upload_dir) else True

    def test_rejects_batch_exceeding_max_file_count(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        uploads = [
            (io.BytesIO(PDF_BYTES), f"doc{i}.pdf", "application/pdf")
            for i in range(MAX_FILES_PER_UPLOAD + 1)
        ]
        success, message, session = adapter.handle_upload(uploads)
        assert success is False
        assert str(MAX_FILES_PER_UPLOAD) in message

    def test_rejects_empty_upload_list(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload([])
        assert success is False
        assert session is None


BROKEN_PDF = b"%PDF-1.7\n" + os.urandom(4000)


def _encrypted_pdf():
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    return data


class TestPdfCheckAtUpload:
    """A file that has the %PDF header but can't be printed is turned away on the phone,
    with the same reason the file browser would give at the kiosk."""

    def test_rejects_a_damaged_pdf(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(BROKEN_PDF), "report.pdf", "application/pdf")]
        )
        assert success is False
        assert session is None
        assert "report.pdf" in message
        assert "damaged" in message

    def test_rejects_a_password_protected_pdf(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(_encrypted_pdf()), "secret.pdf", "application/pdf")]
        )
        assert success is False
        assert "password-protected" in message

    def test_a_rejected_file_leaves_nothing_on_disk(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        adapter.handle_upload([(io.BytesIO(BROKEN_PDF), "report.pdf", "application/pdf")])
        assert os.listdir(upload_dir) == []

    def test_one_bad_file_rejects_the_batch_and_removes_the_good_ones(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload([
            (io.BytesIO(PDF_BYTES), "good.pdf", "application/pdf"),
            (io.BytesIO(BROKEN_PDF), "bad.pdf", "application/pdf"),
        ])
        assert success is False
        assert "bad.pdf" in message
        assert os.listdir(upload_dir) == []

    def test_a_multi_page_pdf_still_passes(self, tmp_path):
        adapter, db, upload_dir = _make_adapter(tmp_path)
        success, message, session = adapter.handle_upload(
            [(io.BytesIO(_real_pdf(pages=5)), "five.pdf", "application/pdf")]
        )
        assert success is True
