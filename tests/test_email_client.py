"""
ImapClient/SmtpClient against a server that accepts the connection and then
never answers, which is what a network dropping mid-connection looks like.
Without a socket timeout the email poller thread blocks there forever and
email intake stops until the app restarts; with one, the call fails and the
poller's next cycle tries again.
"""
import socket
import threading
import time
from email.message import EmailMessage

import pytest

from managers.adapters.email_client import ImapClient, SmtpClient

TIMEOUT = 0.5


@pytest.fixture
def silent_server():
    """A TCP server that accepts connections and never sends a byte."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen()
    accepted = []
    stop = threading.Event()

    def accept_loop():
        server.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                accepted.append(conn)
            except OSError:
                continue

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    yield server.getsockname()[1]
    stop.set()
    thread.join(timeout=1)
    for conn in accepted:
        conn.close()
    server.close()


def _assert_gives_up(call):
    start = time.monotonic()
    with pytest.raises(OSError):  # socket.timeout is an OSError
        call()
    assert time.monotonic() - start < TIMEOUT * 6


def test_imap_gives_up_on_a_silent_server(silent_server):
    client = ImapClient("127.0.0.1", silent_server, "u", "p", use_ssl=False, timeout=TIMEOUT)

    def poll():
        with client:
            pass

    _assert_gives_up(poll)


def test_smtp_gives_up_on_a_silent_server(silent_server):
    client = SmtpClient("127.0.0.1", silent_server, "u", "p", use_ssl=False, timeout=TIMEOUT)
    msg = EmailMessage()
    msg["To"] = "a@example.com"
    msg.set_content("x")
    _assert_gives_up(lambda: client.send(msg))


def test_default_timeout_is_set():
    assert ImapClient("h", 1, "u", "p").timeout > 0
    assert SmtpClient("h", 1, "u", "p").timeout > 0
