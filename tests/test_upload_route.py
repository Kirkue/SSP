"""
Integration tests for GET/POST /upload — drives the FastAPI route in-process
via TestClient (no real Uvicorn socket). The get_wifi_adapter dependency is
overridden with one wired to a temp dir and the same in-memory FakeDBManager
used elsewhere, so no real filesystem location or SQLite DB is touched.
"""
import os

import fitz
from SSP.webapp.main import app
from fastapi.testclient import TestClient
from webapp.dependencies import get_wifi_adapter

from managers.adapters.wifi_adapter import WifiAdapter
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

client = TestClient(app)


def _override_with_temp_adapter(tmp_path):
    db = FakeDBManager()
    adapter = WifiAdapter(SessionManager(db), str(tmp_path / "uploads"), 1024 * 1024)

    def _get():
        yield adapter

    return _get


class TestUploadForm:
    def test_get_upload_returns_form(self):
        response = client.get("/upload")
        assert response.status_code == 200
        assert "<form" in response.text


class TestUploadSuccessPage:
    """The success page carries the QR image, so it also has to help the QR reader read it."""

    @staticmethod
    def _success_html(tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            return client.post(
                "/upload",
                files=[("files", ("document.pdf", PDF_BYTES, "application/pdf"))],
            ).text
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

    def test_shows_brightness_reminder_next_to_the_qr_image(self, tmp_path):
        html = self._success_html(tmp_path)

        reminder = html.index("screen brightness")
        assert html.index('alt="QR"') < reminder < html.index('id="otp-display"')

    def test_requests_a_screen_wake_lock_and_re_requests_when_visible_again(self, tmp_path):
        html = self._success_html(tmp_path)

        assert "navigator.wakeLock.request" in html
        assert "visibilitychange" in html


class TestPostUpload:
    def test_valid_pdf_returns_otp_and_qr(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[("files", ("document.pdf", PDF_BYTES, "application/pdf"))],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 200
        assert 'id="otp-display"' in response.text
        assert "data:image/png;base64," in response.text

    def test_multiple_valid_pdfs_returns_otp_and_qr_with_all_filenames(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[
                    ("files", ("a.pdf", PDF_BYTES, "application/pdf")),
                    ("files", ("b.pdf", PDF_BYTES, "application/pdf")),
                ],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 200
        assert "a.pdf" in response.text
        assert "b.pdf" in response.text

    def test_non_pdf_rejected_with_400(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[("files", ("document.png", b"not a pdf", "image/png"))],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400

    def test_fake_pdf_extension_without_magic_bytes_rejected(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[("files", ("document.pdf", b"not really a pdf", "application/pdf"))],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400

    def test_batch_rejected_with_400_if_any_file_invalid(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[
                    ("files", ("good.pdf", PDF_BYTES, "application/pdf")),
                    ("files", ("bad.pdf", b"not a pdf", "application/pdf")),
                ],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400
        assert os.listdir(tmp_path / "uploads") == [] if (tmp_path / "uploads").is_dir() else True


class TestUploadRejectsUnprintablePdf:
    def test_shows_the_reason_on_the_upload_page(self, tmp_path):
        app.dependency_overrides[get_wifi_adapter] = _override_with_temp_adapter(tmp_path)
        try:
            response = client.post(
                "/upload",
                files=[("files", ("broken.pdf", b"%PDF-1.7\n" + os.urandom(4000), "application/pdf"))],
            )
        finally:
            app.dependency_overrides.pop(get_wifi_adapter, None)

        assert response.status_code == 400
        assert "broken.pdf" in response.text
        assert "damaged" in response.text
