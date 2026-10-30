"""
"Check voucher balance" popup, opened from the homepage and driven through the real
HomepageController and VoucherBalanceController (offscreen Qt) against a temp SQLite DB,
with Vouchers issued by the real VoucherManager.issue() path.

Only main_app is faked: a real QStackedWidget plus show_screen()'s leave/enter lifecycle
(which closes the popup), the timeout manager on a fake clock, and the session's
remembered Vouchers.
"""
import locale
import os
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QStackedWidget, QWidget  # noqa: E402

import managers.voucher_manager as vm  # noqa: E402
import screens.voucher_balance.model as balance_module  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.session_vouchers import SessionVouchers  # noqa: E402
from managers.timeout_manager import TimeoutManager  # noqa: E402
from managers.voucher_manager import MSG_FULLY_USED, MSG_UNKNOWN, VoucherManager, normalize_code  # noqa: E402
from screens.homepage.controller import HomepageController  # noqa: E402
from screens.voucher_balance.controller import VoucherBalanceController  # noqa: E402
from screens.voucher_balance.model import MSG_EMPTY, PESO  # noqa: E402


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class FakeMainApp:
    """Just enough of PrintingSystemApp: a real stack, show_screen()'s lifecycle (which
    closes the popup and clears the remembered Vouchers at idle), and the popup itself."""

    def __init__(self):
        self.window = QWidget()
        self.window.resize(1000, 800)
        self.stacked_widget = QStackedWidget(self.window)
        self.screens = []
        self.timeclock = SimpleNamespace(now=1000.0)
        self.timeouts = TimeoutManager(clock=lambda: self.timeclock.now)
        self.timeouts.expired.connect(lambda name, action: action() if action else None)
        self.session_vouchers = SessionVouchers()
        self.homepage_screen = HomepageController(self)
        self._by_name = {'homepage': self.homepage_screen}
        for widget in self._by_name.values():
            self.stacked_widget.addWidget(widget)
        self.voucher_balance = VoucherBalanceController(self, parent_widget=self.window)

    def open_voucher_balance(self):
        self.voucher_balance.open()

    def show_screen(self, name):
        self.voucher_balance.close()
        current = self.stacked_widget.currentWidget()
        if self.screens and current is not None:
            current.on_leave()
        self.screens.append(name)
        if name == 'idle':
            self.session_vouchers.clear()
        widget = self._by_name.get(name)
        if widget is None:
            self.timeouts.enter(name, None)
            return  # idle/usb/...: not part of these tests
        self.stacked_widget.setCurrentWidget(widget)
        make_policy = getattr(widget, 'timeout_policy', None)
        self.timeouts.enter(name, make_policy() if make_policy else None)
        widget.on_enter()

    def advance_time(self, seconds):
        self.timeclock.now += seconds
        self.timeouts.poll()


@pytest.fixture(scope='module')
def qapp():
    # See test_payment_change_flow.py: QApplication() would localise strftime.
    saved = locale.setlocale(locale.LC_ALL)
    app = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def db(db_path):
    manager = DatabaseManager(db_path=db_path)
    yield manager
    manager.close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def issue(db, clock, monkeypatch):
    """Issue a Voucher the way the payment screen does (VoucherManager.issue)."""
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())
    return lambda value: VoucherManager(db, now_fn=clock).issue(value)


@pytest.fixture
def kiosk(qapp, db, clock, monkeypatch):
    monkeypatch.setattr(balance_module, 'DatabaseManager', lambda *a, **k: db)
    main_app = FakeMainApp()
    # The model builds its own VoucherManager(DatabaseManager()); only its clock is swapped.
    main_app.voucher_balance.model.voucher_manager._now = clock
    main_app.show_screen('homepage')
    main_app.window.show()
    yield main_app
    main_app.voucher_balance.close()
    main_app.homepage_screen.on_leave()
    main_app.timeouts._timer.stop()
    main_app.window.close()


def open_balance_check(main_app):
    main_app.homepage_screen.view.voucher_balance_button.click()
    assert main_app.voucher_balance.is_open
    return main_app.voucher_balance


def check(screen, code):
    screen.view.code_input.setText(code)
    screen.view.check_button.click()
    view = screen.view
    return {
        'found': not view.result_panel.isHidden(),
        'amount': view.amount_label.text(),
        'expiry': view.expiry_label.text(),
        'error': view.status_banner._label.text() if not view.status_banner.isHidden() else "",
    }


def voucher_row(db_path, voucher_id):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT remaining_value, expires_at FROM vouchers WHERE voucher_id = ?", (voucher_id,)
        ).fetchone()
    finally:
        conn.close()


def application_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM voucher_applications").fetchone()[0]
    finally:
        conn.close()


class TestPopup:
    def test_opens_over_the_homepage_without_leaving_it(self, kiosk):
        open_balance_check(kiosk)
        assert kiosk.screens == ['homepage']       # no screen change, nothing started
        assert kiosk.stacked_widget.currentWidget() is kiosk.homepage_screen

    def test_covers_the_whole_window_so_nothing_underneath_can_be_tapped(self, kiosk):
        screen = open_balance_check(kiosk)
        assert screen.view.geometry() == kiosk.window.rect()

    def test_close_button_closes_it_and_stays_on_the_homepage(self, kiosk):
        screen = open_balance_check(kiosk)
        screen.view.close_button.click()
        assert not screen.is_open
        assert kiosk.screens == ['homepage']

    def test_closing_wipes_the_result(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        screen.view.close_button.click()
        assert screen.view.amount_label.text() == ""
        assert screen.view.result_panel.isHidden()
        assert screen.model.remaining == 0

    def test_reopening_starts_empty(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        screen.view.close_button.click()
        screen = open_balance_check(kiosk)
        assert screen.view.result_panel.isHidden() and screen.view.code_input.text() == ""

    def test_any_screen_change_closes_it(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        kiosk.show_screen('idle')
        assert not screen.is_open
        assert screen.view.amount_label.text() == ""

    def test_it_cannot_be_left_open_behind_a_timeout(self, kiosk):
        """The screen underneath times out as normal; that navigation closes the popup."""
        screen = open_balance_check(kiosk)
        kiosk.advance_time(60)
        assert kiosk.screens[-1] == 'idle'
        assert not screen.is_open

    def test_the_reader_hint_tells_customers_they_can_scan(self, kiosk):
        from ui.widgets import READER_HINT
        screen = open_balance_check(kiosk)
        assert screen.view.reader_hint.text() == READER_HINT
        assert "QR" in READER_HINT


class TestRememberedVouchers:
    """A Voucher that checks out is kept for the session so payment can offer it."""

    def test_a_found_voucher_is_remembered(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        [remembered] = kiosk.session_vouchers.items()
        assert remembered.code == normalize_code(v.code)
        assert remembered.remaining == 7
        assert remembered.expires_at.year == 2026

    def test_the_popup_says_it_was_saved(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        assert "Saved for this session" in screen.view.saved_note.text()

    def test_the_qr_form_is_remembered_too(self, kiosk, issue):
        v = issue(7)
        open_balance_check(kiosk).check_voucher_code(f"V1:{v.code}")
        assert [r.code for r in kiosk.session_vouchers.items()] == [v.code]

    def test_failed_checks_are_not_remembered(self, kiosk, issue, db, clock):
        used = issue(4)
        VoucherManager(db, now_fn=clock).apply([used.code], 4)
        screen = open_balance_check(kiosk)
        check(screen, used.display_code)
        check(screen, "ZZZZ-ZZZZ")
        check(screen, "  ")
        assert kiosk.session_vouchers.items() == []

    def test_several_are_kept_in_the_order_checked(self, kiosk, issue):
        a, b = issue(5), issue(9)
        screen = open_balance_check(kiosk)
        check(screen, a.display_code)
        check(screen, b.display_code)
        assert [r.remaining for r in kiosk.session_vouchers.items()] == [5, 9]

    def test_checking_again_refreshes_the_balance(self, kiosk, issue, db, clock):
        v = issue(10)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        VoucherManager(db, now_fn=clock).apply([v.code], 4)
        check(screen, v.display_code)
        assert [r.remaining for r in kiosk.session_vouchers.items()] == [6]

    def test_they_survive_closing_the_popup_but_not_going_back_to_idle(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        screen.view.close_button.click()
        assert len(kiosk.session_vouchers) == 1
        kiosk.show_screen('idle')
        assert len(kiosk.session_vouchers) == 0

    def test_they_are_never_applied_by_checking(self, kiosk, issue, db_path):
        v = issue(7)
        before = voucher_row(db_path, v.voucher_id)
        check(open_balance_check(kiosk), v.display_code)
        assert voucher_row(db_path, v.voucher_id) == before
        assert application_count(db_path) == 0


class TestBalance:
    def test_shows_remaining_value_and_expiry(self, kiosk, issue):
        v = issue(7)  # issued 2026-10-01, 30-day expiry
        shown = check(open_balance_check(kiosk), v.display_code)
        assert shown == {
            'found': True, 'amount': f"{PESO}7",
            'expiry': "Valid until October 31, 2026", 'error': "",
        }

    def test_shows_partly_used_remaining_value(self, kiosk, issue, db, clock):
        v = issue(10)
        VoucherManager(db, now_fn=clock).apply([v.code], 4)
        assert check(open_balance_check(kiosk), v.display_code)['amount'] == f"{PESO}6"

    def test_typed_code_is_cleared_once_found(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        check(screen, v.display_code)
        assert screen.view.code_input.text() == ""

    def test_code_typed_on_the_keypad_is_checked(self, kiosk, issue):
        from ui.widgets import BACKSPACE_KEY
        v = issue(7)
        screen = open_balance_check(kiosk)
        keys = screen.view.keypad.key_buttons
        assert set(keys) == set(vm.CODE_ALPHABET) | {BACKSPACE_KEY}
        keys["Z"].click()
        keys[BACKSPACE_KEY].click()
        for ch in v.code:
            keys[ch].click()
        screen.view.check_button.click()
        assert not screen.view.result_panel.isHidden()
        assert screen.view.amount_label.text() == f"{PESO}7"

    def test_accepts_the_qr_payload_form(self, kiosk, issue):
        v = issue(7)
        assert check(open_balance_check(kiosk), f"V1:{v.code}")['found']

    def test_qr_read_is_checked(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        screen.check_voucher_code(f"V1:{v.code}")  # what main_app hands a Voucher read
        assert not screen.view.result_panel.isHidden()
        assert screen.view.amount_label.text() == f"{PESO}7"

    def test_expired_fully_used_and_unknown_get_distinct_messages(self, kiosk, issue, db, clock):
        used = issue(4)
        VoucherManager(db, now_fn=clock).apply([used.code], 4)
        expired = issue(9)
        clock.advance(days=31)
        screen = open_balance_check(kiosk)
        shown = {
            'used': check(screen, used.display_code),
            'expired': check(screen, expired.display_code),
            'unknown': check(screen, "ZZZZ-ZZZZ"),
        }
        assert not any(s['found'] for s in shown.values())
        assert shown['used']['error'] == MSG_FULLY_USED
        assert shown['expired']['error'] == "This voucher expired on October 31, 2026"
        assert shown['unknown']['error'] == MSG_UNKNOWN

    def test_blank_input_asks_for_a_code_without_counting(self, kiosk, db):
        assert check(open_balance_check(kiosk), "  ")['error'] == MSG_EMPTY
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0

    def test_never_changes_value_or_expiry(self, kiosk, issue, db_path):
        v = issue(7)
        before = voucher_row(db_path, v.voucher_id)
        screen = open_balance_check(kiosk)
        for _ in range(3):
            check(screen, v.display_code)
        check(screen, f"V1:{v.code}")
        assert voucher_row(db_path, v.voucher_id) == before
        assert application_count(db_path) == 0


class TestSharedLockout:
    def test_three_wrong_here_plus_two_wrong_at_payment_locks(self, kiosk, issue, db, clock):
        v = issue(7)
        screen = open_balance_check(kiosk)
        for _ in range(3):
            assert check(screen, "ZZZZ-ZZZZ")['error'] == MSG_UNKNOWN

        # The payment screen Applies typed codes through VoucherManager.apply (#26).
        at_payment = VoucherManager(db, now_fn=clock)
        assert not at_payment.apply(["ZZZZ-ZZZZ"], 10).locked
        assert at_payment.apply(["ZZZZ-ZZZZ"], 10).locked

        # Locked kiosk-wide: even the right code is refused here, with the cooldown shown.
        shown = check(screen, v.display_code)
        assert not shown['found']
        assert "locked for 5 more minute(s)" in shown['error']
        assert screen.model.locked

        clock.advance(minutes=5, seconds=1)
        assert check(screen, v.display_code)['found']

    def test_wrong_codes_read_here_count_toward_the_shared_lockout(self, kiosk, issue, db, clock):
        v = issue(7)
        screen = open_balance_check(kiosk)
        for _ in range(3):
            screen.check_voucher_code("V1:ZZZZZZZZ")  # what main_app hands a Voucher read
            assert screen.view.status_banner._label.text() == MSG_UNKNOWN

        at_payment = VoucherManager(db, now_fn=clock)
        assert not at_payment.apply(["ZZZZ-ZZZZ"], 10).locked
        assert at_payment.apply(["ZZZZ-ZZZZ"], 10).locked
        screen.check_voucher_code(f"V1:{v.code}")
        assert screen.view.result_panel.isHidden()
        assert screen.model.locked

    def test_malformed_reads_do_not_count_toward_the_lockout(self, kiosk, issue):
        v = issue(7)
        screen = open_balance_check(kiosk)
        for _ in range(vm.MAX_FAILED_ATTEMPTS + 1):
            screen.check_voucher_code("V1:HELLO")
        assert not screen.model.locked
        screen.check_voucher_code(f"V1:{v.code}")
        assert not screen.view.result_panel.isHidden()
