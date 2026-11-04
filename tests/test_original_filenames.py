"""
Wi-Fi and email uploads are stored as <uuid>.pdf so a hostile filename can't
escape the upload directory, but the customer should see the name their file
had: in the file browser, on the payment summary, and in transactions.file_name.
"""
import email
import os
import tempfile
from email.message import EmailMessage
from unittest.mock import MagicMock

import fitz
import pytest

from managers.adapters.email_adapter import EmailAdapter, attachment_filename
from managers.usb_file_manager import USBFileManager, display_filename
from screens.payment.model import _document_name


def _pdf_bytes():
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path / 'tmp'))
    up = tmp_path / 'uploads'
    up.mkdir()
    paths = []
    for name in ('a1b2c3.pdf', 'd4e5f6.pdf'):
        (up / name).write_bytes(_pdf_bytes())
        paths.append(str(up / name))
    return paths


def test_session_files_show_their_original_names(uploads):
    files = USBFileManager().scan_and_copy_pdf_files_by_paths(
        uploads, ['Thesis Final.pdf', 'Thesis Final.pdf'])

    assert [f['filename'] for f in files] == ['Thesis Final.pdf', 'Thesis Final.pdf']
    # Same-named uploads still get separate copies.
    assert len({f['path'] for f in files}) == 2
    assert all(os.path.exists(f['path']) for f in files)


def test_a_file_with_no_usable_name_falls_back_to_the_stored_name(uploads):
    files = USBFileManager().scan_and_copy_pdf_files_by_paths(uploads, [None, '  '])

    assert [f['filename'] for f in files] == ['a1b2c3.pdf', 'd4e5f6.pdf']


def test_no_display_names_keeps_the_stored_names(uploads):
    files = USBFileManager().scan_and_copy_pdf_files_by_paths(uploads)

    assert [f['filename'] for f in files] == ['a1b2c3.pdf', 'd4e5f6.pdf']


@pytest.mark.parametrize('original, expected', [
    ('report.pdf', 'report.pdf'),
    ('C:\\Users\\me\\Desktop\\report.pdf', 'report.pdf'),
    ('../../etc/passwd.pdf', 'passwd.pdf'),
    ('bad\nname.pdf', 'badname.pdf'),
    ('', 'stored.pdf'),
    (None, 'stored.pdf'),
    ('dir/', 'stored.pdf'),
])
def test_display_filename(original, expected):
    assert display_filename(original, 'stored.pdf') == expected


def test_payment_uses_the_original_name_not_the_stored_one():
    pdf_data = {'path': '/tmp/x/0f3a9c.pdf', 'filename': 'Resume.pdf'}
    assert _document_name(pdf_data) == 'Resume.pdf'
    assert _document_name({'path': '/tmp/x/0f3a9c.pdf'}) == '0f3a9c.pdf'


def _email_with_attachment(filename_header):
    # Raw bytes as a mail client sends them, parsed the way EmailAdapter does
    # (compat32 policy), which leaves RFC 2047 encoded-words undecoded.
    raw = (
        'Content-Type: multipart/mixed; boundary="b"\r\nSubject: print\r\n\r\n'
        '--b\r\nContent-Type: application/pdf\r\n'
        f'Content-Disposition: attachment; filename="{filename_header}"\r\n\r\n'
        '%PDF\r\n--b--\r\n'
    ).encode()
    parsed = email.message_from_bytes(raw)
    return next(p for p in parsed.walk() if p.get_content_type() == 'application/pdf')


def test_email_attachment_name_decodes_encoded_words():
    part = _email_with_attachment('=?UTF-8?B?UmVzdW3DqS5wZGY=?=')
    assert attachment_filename(part) == 'Resumé.pdf'


def test_email_attachment_plain_name():
    assert attachment_filename(_email_with_attachment('notes.pdf')) == 'notes.pdf'


def test_email_session_records_the_attachment_name(tmp_path):
    msg = EmailMessage()
    msg['Subject'] = 'print'
    msg['From'] = 'a@example.com'
    msg.set_content('hi')
    msg.add_attachment(_pdf_bytes(), maintype='application', subtype='pdf',
                       filename='Lab Report.pdf')
    sessions = MagicMock()
    adapter = EmailAdapter.__new__(EmailAdapter)
    adapter.subject_keyword = 'print'
    adapter.max_size_bytes = 10 * 1024 * 1024
    adapter.upload_dir = str(tmp_path)
    adapter.session_manager = sessions

    adapter._handle_message(msg.as_bytes())

    files = sessions.create_session.call_args.kwargs['files']
    assert files[0]['original_filename'] == 'Lab Report.pdf'
