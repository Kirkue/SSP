"""
Seam tests for PrintingSystemApp._on_qr_read: a raw read on a given screen is
de-duplicated, decided, and handed to the right screen. The screens are
recorders; decide_qr_read and a real SessionManager on a temp SQLite
database do the deciding. Voucher handling itself is covered by
test_payment_change_flow.py and test_voucher_balance.py.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from main_app import PrintingSystemApp  # noqa: E402
from managers.qr_reader import DuplicateReadFilter, MSG_VOUCHER_AT_PAYMENT  # noqa: E402
from managers.session_manager import SessionManager  # noqa: E402


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, *args))


class BalancePopup:
    """The "Check voucher balance" popup: open or closed, recording the reads it's handed."""

    def __init__(self):
        self.is_open = False
        self.calls = []

    def check_voucher_code(self, text):
        self.calls.append(("check_voucher_code", text))


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def sessions(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    db = DatabaseManager(db_path=db_path)
    yield SessionManager(db)
    db.conn.close()


@pytest.fixture
def app(sessions):
    """Just the attributes _on_qr_read touches, with the read landing on `app.screen`."""
    clock = FakeClock()
    current = Recorder()
    fake = SimpleNamespace(
        screen="payment",
        clock=clock,
        current=current,
        payment_screen=Recorder(),
        voucher_balance=BalancePopup(),
        opened=[],
        activity=[],
        qr_session_manager=sessions,
        _qr_duplicates=DuplicateReadFilter(window_seconds=3, clock=clock),
        stacked_widget=SimpleNamespace(currentWidget=lambda: current),
    )
    fake._current_screen_name = lambda: fake.screen
    fake._qr_context = lambda: PrintingSystemApp._qr_context(fake)
    fake.note_activity = lambda: fake.activity.append(1)
    fake.open_session_files = lambda source, files: fake.opened.append(source) or True
    fake.read = lambda text: PrintingSystemApp._on_qr_read(fake, text)
    return fake


def test_any_read_counts_as_activity_so_the_screen_does_not_time_out(app):
    """Someone is at the kiosk, whether or not the read is accepted or a repeat."""
    app.read("V1:ABCD1234")
    app.clock.now += 1
    app.read("V1:ABCD1234")      # a duplicate, dropped
    app.read("not a known payload")
    assert len(app.activity) == 3


def test_voucher_read_on_payment_is_applied(app):
    app.read("V1:ABCD1234")
    assert app.payment_screen.calls == [("apply_voucher_code", "V1:ABCD1234")]
    assert app.voucher_balance.calls == []
    assert app.current.calls == []


@pytest.mark.parametrize("screen", ["homepage", "printing_options"])
def test_voucher_read_with_the_balance_popup_open_checks_the_balance(app, screen):
    """The popup wins over whatever screen is underneath."""
    app.screen = screen
    app.voucher_balance.is_open = True
    app.read("V1:ABCD1234")
    assert app.voucher_balance.calls == [("check_voucher_code", "V1:ABCD1234")]
    assert app.payment_screen.calls == []
    assert app.current.calls == []


def test_closing_the_popup_restores_the_screens_own_behaviour(app):
    app.screen = "homepage"
    app.voucher_balance.is_open = True
    app.read("V1:AAAA1111")
    app.voucher_balance.is_open = False
    app.clock.now += 5
    app.read("V1:BBBB2222")
    assert app.voucher_balance.calls == [("check_voucher_code", "V1:AAAA1111")]
    assert app.current.calls == [("show_qr_message", MSG_VOUCHER_AT_PAYMENT)]


def test_a_voucher_read_on_payment_applies_it_there(app):
    """Payment has no balance popup: a read applies the voucher, as before."""
    app.screen = "payment"
    app.read("V1:ABCD1234")
    assert app.payment_screen.calls == [("apply_voucher_code", "V1:ABCD1234")]
    assert app.voucher_balance.calls == []


@pytest.mark.parametrize("screen", ["idle", "homepage", "wifi", "email"])
def test_voucher_read_elsewhere_says_vouchers_are_for_payment(app, screen):
    app.screen = screen
    app.read("V1:ABCD1234")
    assert app.current.calls == [("show_qr_message", MSG_VOUCHER_AT_PAYMENT)]
    assert app.payment_screen.calls == []
    assert app.voucher_balance.calls == []


def test_several_voucher_reads_on_payment_are_applied_in_the_order_read(app):
    for text in ("V1:AAAA1111", "V1:BBBB2222", "V1:CCCC3333"):
        app.read(text)
    assert [args for _, *args in app.payment_screen.calls] == [
        ["V1:AAAA1111"], ["V1:BBBB2222"], ["V1:CCCC3333"]]


def test_repeat_read_within_the_window_is_applied_once(app):
    app.read("V1:ABCD1234")
    app.clock.now += 1
    app.read("V1:ABCD1234")
    assert len(app.payment_screen.calls) == 1


@pytest.mark.parametrize("where", ["payment", "balance_popup"])
def test_voucher_screens_ignore_session_and_malformed_reads(app, sessions, where):
    if where == "payment":
        app.screen = "payment"
    else:
        app.screen = "homepage"
        app.voucher_balance.is_open = True
    session = sessions.create_session("wifi", [{"path": "/tmp/a.pdf", "original_filename": "a.pdf"}])
    app.read(f"{session.session_id}:{session.otp}")
    app.read("garbage")
    assert app.payment_screen.calls == app.voucher_balance.calls == app.current.calls == []
    assert app.opened == []
