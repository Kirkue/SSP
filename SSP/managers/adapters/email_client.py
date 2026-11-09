# managers/adapters/email_client.py
#
# Thin protocol wrappers around imaplib/smtplib. EmailAdapter depends on
# these (not on imaplib/smtplib directly) so its polling and reply logic
# can be tested against a fake, the same way SessionManager is tested
# against a fake DatabaseManager. Greenmail (dev) and the eventual
# dedicated Gmail account are both just EMAIL_* config values passed to
# the constructors here — no code branches on which one is in use.

import imaplib
import re
import smtplib
from email.message import EmailMessage
from typing import List, Tuple

_UIDVALIDITY_RE = re.compile(rb"UIDVALIDITY (\d+)")

# Seconds any one socket operation may wait. Without it, a network that drops
# mid-connection blocks the email poller thread forever and email intake stops
# until the app restarts; with it the call fails and the next poll cycle retries.
DEFAULT_TIMEOUT_SECONDS = 30


class ImapClient:
    """
    Opens a fresh IMAP connection per `with` block rather than holding one
    open across poll cycles — simpler reconnect story if the network drops
    between polls (relevant over the SIM7600G-H's 4G data path).
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 use_ssl: bool = True, mailbox: str = "INBOX",
                 timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.mailbox = mailbox
        self.timeout = timeout
        self._conn = None

    def __enter__(self):
        conn_cls = imaplib.IMAP4_SSL if self.use_ssl else imaplib.IMAP4
        self._conn = conn_cls(self.host, self.port, timeout=self.timeout)
        self._conn.login(self.username, self.password)
        self._conn.select(self.mailbox)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._conn is not None:
            try:
                self._conn.logout()
            except OSError:
                pass
            self._conn = None

    def search_unseen(self) -> Tuple[int, List[int]]:
        """Returns (uidvalidity, [uid, ...]) for unseen messages in the selected mailbox."""
        status, data = self._conn.status(self.mailbox, "(UIDVALIDITY)")
        if status != "OK" or not data or not data[0]:
            raise RuntimeError(f"Failed to read UIDVALIDITY for '{self.mailbox}'")
        match = _UIDVALIDITY_RE.search(data[0])
        if not match:
            raise RuntimeError(f"Could not parse UIDVALIDITY from: {data[0]!r}")
        uidvalidity = int(match.group(1))

        status, data = self._conn.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("UID SEARCH UNSEEN failed")
        uids = [int(u) for u in data[0].split()] if data and data[0] else []
        return uidvalidity, uids

    def fetch(self, uid: int) -> bytes:
        """Returns the raw RFC822 bytes for a UID."""
        status, msg_data = self._conn.uid("fetch", str(uid), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            raise RuntimeError(f"Failed to fetch UID {uid}")
        return msg_data[0][1]

    def mark_seen(self, uid: int):
        self._conn.uid("store", str(uid), "+FLAGS", "(\\Seen)")


class SmtpClient:
    def __init__(self, host: str, port: int, username: str, password: str, use_ssl: bool = True,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.timeout = timeout

    def send(self, msg: EmailMessage):
        # SMTP_SSL covers Gmail's port 465. Greenmail's plain test port needs
        # neither TLS nor real credentials, so use_ssl=False just skips it —
        # add STARTTLS (port 587) here later if a deployment needs it instead.
        smtp_cls = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_cls(self.host, self.port, timeout=self.timeout) as server:
            server.login(self.username, self.password)
            server.send_message(msg)
