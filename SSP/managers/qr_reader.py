# managers/qr_reader.py
#
# The kiosk's QR reader (see CONTEXT.md and ADR 0004): a cheap embedded 2D
# module run as a USB serial port. Not the flatbed document scanner — that's
# managers/scanner.py.
#
# Three pieces, all free of Qt so they can be tested without an event loop:
#   - QrReaderManager: background thread that re-asserts the reader's config on
#     every port open, then frames the serial stream into CR-terminated reads
#     and hands each one to a callback.
#   - classify_payload(): every read is untrusted (anyone can reconfigure the
#     reader), so it's checked against exact formats before anything acts on it.
#   - decide_qr_read(): classified read + current screen + SessionManager
#     -> what the app should do.

import re
import threading
import time
from dataclasses import dataclass

from config import get_config

try:
    import serial
except ImportError:  # pyserial is optional unless a reader port is configured
    serial = None

READER_BAUDRATE = 9600  # ignored by a USB CDC port, but pyserial wants one
_POLL_TIMEOUT_SECONDS = 0.1
_JOIN_TIMEOUT_SECONDS = 2.0
DEFAULT_RETRY_SECONDS = 5.0
# The bench reader takes 0.42-0.58 s to answer each command (2026-10-01), so the
# full send takes ~8 s; reads that arrive meanwhile are held until it ends.
DEFAULT_REPLY_TIMEOUT_SECONDS = 1.5

# The reader's settings, sent as `#<code>;` each time the port opens so a
# settings barcode a customer showed it is undone (ADR 0004). Each command looks
# like a flash write: send on open only, never on a timer.
KIOSK_CONFIG = (
    "JA060",  # USB COM
    "DC010",  # Auto-Sensing
    "AB060",  # 2D-ON
    "AB030",  # 1D-OFF
    "DK010",  # End Mark CR
    "DN030",  # Duplicate Detection ON (its time is NAKed over serial: see DuplicateReadFilter)
    "JD040",  # No Swap
    "DF000",  # Display Prefix OFF
    "DG000",  # Display Suffix OFF
    "DP020",  # Delete Characters OFF
    "JD060",  # Invoice Function OFF
    "CD010",  # Volume ON
    "CD032",  # Low Volume
)
# Restore Defaults and keyboard mode: either one removes the serial port.
NEVER_SEND = frozenset({"AB160", "JA020"})
# One-byte replies to a command. They aren't CR-terminated, so they share the read stream.
ACK = 0x06
NAK = 0x15
_REPLY_BYTES = bytes((ACK, NAK))

# Reader availability, as reported by QrReaderManager.status
CONNECTED = "connected"
UNAVAILABLE = "unavailable"

# fullmatch + [0-9]/[0-9a-f] (not \d or $) so a trailing newline, whitespace,
# uppercase hex or non-ASCII digits are all malformed.
_SESSION_PAYLOAD = re.compile(r"([0-9a-f]{16}):([0-9]{6})")
_VOUCHER_PREFIX = "V1:"

# Screens that accept a read (and can show a message about it). Every other
# screen ignores reads silently.
_ACCEPTING_SCREENS = {"idle", "homepage", "wifi", "email"}
# Screens that take a Voucher payload, and what to do with it there. They
# ignore every other read silently. "voucher_balance" is the balance popup, not a
# screen: main_app passes it as the context while the popup is open (_qr_context).
_VOUCHER_SCREENS = {"payment": "apply_voucher", "voucher_balance": "check_voucher"}
_KIOSK_SOURCES = {"wifi", "email"}

DUPLICATE_WINDOW_SECONDS = 3.0

MSG_CANT_READ = "Couldn't read that, type your code."
MSG_CANT_USE_HERE = "This code can't be used here."
MSG_VOUCHER_AT_PAYMENT = "Vouchers can only be used at payment."
# Same wording a typed code gets for a session that is gone or already used.
MSG_NOT_FOUND_OR_USED = "Incorrect or expired code"


@dataclass
class QrRead:
    kind: str  # 'session' | 'voucher' | 'malformed'
    session_id: str = None
    otp: str = None


@dataclass
class QrReadOutcome:
    # 'open_files' | 'rejected' (show `message`) | 'ignore' (silent)
    # | 'apply_voucher' / 'check_voucher' (hand the read's text to that screen)
    action: str
    source: str = None
    files: list = None
    message: str = None


def classify_payload(text: str) -> QrRead:
    match = _SESSION_PAYLOAD.fullmatch(text)
    if match:
        return QrRead("session", session_id=match.group(1), otp=match.group(2))
    if text.startswith(_VOUCHER_PREFIX):
        return QrRead("voucher")
    return QrRead("malformed")


def decide_qr_read(read: QrRead, screen: str, session_manager) -> QrReadOutcome:
    """Decide what a read means on `screen`. Only a well-formed Session payload
    on an accepting screen can touch the Session Manager; malformed reads,
    Voucher payloads and wrong-Source Sessions never count as a failed attempt.
    A Voucher payload is only checked by the screen it's handed to, where a
    wrong code counts toward the Voucher lockout just as a typed one does."""
    if screen in _VOUCHER_SCREENS:
        return QrReadOutcome(_VOUCHER_SCREENS[screen] if read.kind == "voucher" else "ignore")
    if screen not in _ACCEPTING_SCREENS:
        return QrReadOutcome("ignore")
    if read.kind == "voucher":
        return QrReadOutcome("rejected", message=MSG_VOUCHER_AT_PAYMENT)
    if read.kind != "session":
        return QrReadOutcome("rejected", message=MSG_CANT_READ)

    # Checked before verification so a wrong-source Session never gets an attempt counted.
    source = session_manager.get_session_source(read.session_id)
    if source is None:
        return QrReadOutcome("rejected", message=MSG_NOT_FOUND_OR_USED)
    if source not in _KIOSK_SOURCES:
        return QrReadOutcome("rejected", message=MSG_CANT_USE_HERE)
    # A typed code never resolves a used Session, so a read must not reopen its files.
    if session_manager.get_session_status(read.session_id) == "verified":
        return QrReadOutcome("rejected", message=MSG_NOT_FOUND_OR_USED)

    success, message, files = session_manager.verify_otp(read.session_id, read.otp)
    if not success:
        return QrReadOutcome("rejected", message=message)
    return QrReadOutcome("open_files", source=source, files=files, message=message)


def describe_reader_status(manager) -> str:
    """Kiosk Admin's one-line reader status. No manager means QR_READER_PORT is
    blank: that's a choice, not a fault."""
    if manager is None:
        return "Not configured"
    return {CONNECTED: "Connected", UNAVAILABLE: "Not connected"}.get(manager.status, "Starting")


def should_log_status_change(new, previous) -> bool:
    """Loss and recovery go to error_log; a healthy first connect doesn't."""
    return new == UNAVAILABLE or previous == UNAVAILABLE


class DuplicateReadFilter:
    """Drops a payload read again within a few seconds of its last accepted
    read, even with other reads in between, so one accidental double read
    doesn't show a 'code already used' error. Suppressed repeats don't extend
    the window. The source of truth for duplicates: the reader's own Duplicate
    Detection time can't be set over serial (ADR 0004)."""

    def __init__(self, window_seconds=DUPLICATE_WINDOW_SECONDS, clock=time.monotonic):
        self._window = window_seconds
        self._clock = clock
        self._accepted_at = {}  # payload -> time of its last accepted read

    def is_duplicate(self, text: str) -> bool:
        now = self._clock()
        # Forget expired payloads so a long-running kiosk doesn't keep every read
        self._accepted_at = {t: at for t, at in self._accepted_at.items() if now - at < self._window}
        if text in self._accepted_at:
            return True
        self._accepted_at[text] = now
        return False


def _split_reads(buffer):
    """CR-terminated reads in `buffer`, and the partial line left over. Stray
    LFs and command replies (a late one can land mid-line) are dropped: neither
    byte is in any valid payload."""
    *lines, rest = buffer.split(b"\r")
    texts = []
    for line in lines:
        text = line.translate(None, b"\n" + _REPLY_BYTES).decode("ascii", errors="replace")
        if text:
            texts.append(text)
    return texts, rest


class QrReaderManager:
    """Reads CR-terminated lines from a serial port on a daemon thread and calls
    `on_read(text)` once per non-empty read. Stray LFs are dropped.

    Each time the port opens, the manager first sends `config` and waits up to
    `reply_timeout` for each code's ACK. Reads that arrive during the send are
    handed on after it. Codes that were NAKed or got no reply are reported by one
    `on_config_error(detail)` call per open; reading carries on regardless.

    The port comes from `open_port()` so it can be reopened: if it can't be
    opened, or disappears mid-run (unplugged, or switched out of serial mode),
    the manager goes UNAVAILABLE and retries every `retry_seconds` until the
    reader is back. `on_status(new, previous)` fires once per change of
    availability, never per retry, so callers can log each change once."""

    def __init__(self, open_port, on_read, on_status=None, retry_seconds=DEFAULT_RETRY_SECONDS,
                 config=KIOSK_CONFIG, on_config_error=None, reply_timeout=DEFAULT_REPLY_TIMEOUT_SECONDS):
        forbidden = NEVER_SEND.intersection(config)
        if forbidden:
            raise ValueError(f"refusing to send reader codes that remove the port: {sorted(forbidden)}")
        self._open_port = open_port
        self._on_read = on_read
        self._on_status = on_status
        self.retry_seconds = retry_seconds
        self._config = tuple(config)
        self._on_config_error = on_config_error
        self._reply_timeout = reply_timeout
        self._status = None  # None until the first open attempt
        self._thread = None
        self._stop_event = threading.Event()

    @property
    def status(self):
        return self._status

    @classmethod
    def from_config(cls, on_read, on_status=None, on_config_error=None):
        """Returns None when QR_READER_PORT is blank (reader off) or pyserial is
        missing. An unopenable port still returns a manager: it keeps retrying."""
        port_name = get_config().qr_reader_port
        if not port_name:
            return None
        if serial is None:
            print("⚠️ QR_READER_PORT is set but pyserial is not installed; QR reader off")
            return None

        def open_port():
            return serial.serial_for_url(port_name, baudrate=READER_BAUDRATE,
                                         timeout=_POLL_TIMEOUT_SECONDS)
        return cls(open_port, on_read, on_status, on_config_error=on_config_error)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="qr-reader", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
            self._thread = None

    def _run(self):
        while not self._stop_event.is_set():
            try:
                port = self._open_port()
            except Exception as e:
                self._set_status(UNAVAILABLE, f"could not open the port: {e}")
                self._stop_event.wait(self.retry_seconds)
                continue
            try:
                self._read_until_lost(port)
            finally:
                self._close(port)
            if not self._stop_event.is_set():
                self._stop_event.wait(self.retry_seconds)

    def _read_until_lost(self, port):
        held = []
        buffer = self._send_config(port, held)  # a partial line dies with the port
        if buffer is None:
            return
        for text in held:
            self._emit(text)
        while not self._stop_event.is_set():
            chunk = self._read_chunk(port)
            if chunk is None:
                return
            texts, buffer = _split_reads(buffer + chunk)
            for text in texts:
                self._emit(text)

    def _send_config(self, port, held):
        """Sends each config code and takes its reply out of the stream. Reads
        that complete meanwhile go into `held`. Returns the partial line left
        over, or None if the port was lost (or stop() was called)."""
        buffer = b""
        failures = []
        for code in self._config:
            if self._stop_event.is_set():
                return None
            try:
                port.write(f"#{code};".encode("ascii"))
            except Exception as e:
                self._set_status(UNAVAILABLE, f"lost the port: {e}")
                return None
            reply = None
            deadline = time.monotonic() + self._reply_timeout
            while reply is None and time.monotonic() < deadline and not self._stop_event.is_set():
                chunk = self._read_chunk(port)
                if chunk is None:
                    return None
                buffer += chunk
                at = next((i for i, byte in enumerate(buffer) if byte in _REPLY_BYTES), None)
                if at is not None:
                    reply, buffer = buffer[at], buffer[:at] + buffer[at + 1:]
                texts, buffer = _split_reads(buffer)
                held.extend(texts)
            if self._stop_event.is_set():
                return None
            if reply != ACK:
                failures.append(f"{code} {'NAK' if reply == NAK else 'no reply'}")
        if failures:
            self._report_config_error(", ".join(failures))
        return buffer

    def _read_chunk(self, port):
        """Bytes from the port (maybe none), or None once the port is lost."""
        try:
            chunk = port.read(port.in_waiting or 1)
        except Exception as e:
            self._set_status(UNAVAILABLE, f"lost the port: {e}")
            return None
        # Only a read that worked proves the reader is there: a stale device
        # node can open fine yet fail every read, and must not flap the status.
        self._set_status(CONNECTED)
        return chunk

    def _report_config_error(self, detail):
        print(f"⚠️ QR reader config not fully applied: {detail}")
        if self._on_config_error is not None:
            try:
                self._on_config_error(detail)
            except Exception as e:
                print(f"⚠️ QR reader config error handler failed: {e}")

    def _set_status(self, status, detail=""):
        if status == self._status:
            return
        previous, self._status = self._status, status
        print(f"{'✅' if status == CONNECTED else '⚠️'} QR reader {status}"
              f"{': ' + detail if detail else ''}")
        if self._on_status is not None:
            try:
                self._on_status(status, previous, detail)
            except Exception as e:
                print(f"⚠️ QR reader status handler failed: {e}")

    @staticmethod
    def _close(port):
        try:
            port.close()
        except Exception as e:
            print(f"⚠️ Error closing QR reader port: {e}")

    def _emit(self, text):
        try:
            self._on_read(text)
        except Exception as e:
            print(f"⚠️ QR read handler failed: {e}")
