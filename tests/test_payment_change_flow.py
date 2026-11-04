"""
End-to-end SIM_MODE tests for change dispensing, Shortfalls and Vouchers:
a real PrintOptionsModel prices a real PDF, a real PaymentModel takes the
payment, auto-completes, dispenses change on the real DispenseThread
(simulated ChangeDispenser), shows the real VoucherController (offscreen),
and logs the transaction to a temp SQLite DB.

Only the edges are faked: the coin/bill acceptor (a per-test stand-in for the
persistent_gpio singleton, which would otherwise outlive each PaymentModel),
main_app (screen navigation, paper check, the timeout manager on a fake clock), the
per-coin hopper call (ChangeDispenser._dispense_coin) when a test needs a
hopper to fail, QR image rendering, and the operator SMS send.
"""
import locale
import os
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import managers.hopper_manager as hm  # noqa: E402
import managers.voucher_manager as vm  # noqa: E402
import screens.payment.model as payment_module  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.session_vouchers import SessionVouchers  # noqa: E402
from managers.timeout_manager import TimeoutManager  # noqa: E402
from managers.voucher_manager import VoucherManager  # noqa: E402
from managers.print_refund import record_print_success, refund_failed_print  # noqa: E402
from screens.payment.model import PaymentModel, ShortfallCause, redirect_for_carried_credit  # noqa: E402
from screens.print_options.model import PrintOptionsModel  # noqa: E402
from screens.voucher.controller import VoucherController  # noqa: E402

PDF = os.path.join(os.path.dirname(__file__), '..', 'test_pdfs', 'Rootlocus-Plotting-1.pdf')


class FakeAcceptors(QObject):
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    def enable_payment(self):
        pass

    def disable_payment(self):
        pass

    def process_coin_timeout(self):
        pass


class FakeAdminScreen:
    def check_paper_availability(self, pages):
        return True


class FakeMainApp:
    def __init__(self):
        self.admin_screen = FakeAdminScreen()
        self.db_threader = None
        self.screens = []
        # The real timeout manager on a clock the tests move by hand (advance_time)
        self.clock = SimpleNamespace(now=1000.0)
        self.timeouts = TimeoutManager(clock=lambda: self.clock.now)
        self.timeouts.expired.connect(lambda name, action: action() if action else None)
        self.session_vouchers = SessionVouchers()   # Vouchers checked in the balance popup
        self.payment_screen = SimpleNamespace(model=None)
        self.voucher_screen = VoucherController(self)
        self.scan_result_screen = SimpleNamespace(
            session=None, then_print=None,
            set_session=lambda session, then_print=False: self._set_scan_session(session, then_print))
        self.current_print_job = 'stale'

    def _set_scan_session(self, session, then_print):
        self.scan_result_screen.session = session
        self.scan_result_screen.then_print = then_print

    def show_screen(self, name):
        # Like PrintingSystemApp.show_screen: leave, (abandoned payment -> voucher),
        # hand the new screen's timeout policy to the manager, enter.
        if self.screens and self.screens[-1] == 'voucher':
            self.voucher_screen.on_leave()
        name = redirect_for_carried_credit(self, name)
        self.screens.append(name)
        self.timeouts.enter(name, self.voucher_screen.timeout_policy() if name == 'voucher' else None)
        if name == 'voucher':
            self.voucher_screen.on_enter()

    def note_activity(self):
        self.timeouts.note_activity()

    def end_session(self):
        pass

    def advance_time(self, seconds):
        """Moves the fake clock on and lets the timeout manager notice."""
        self.clock.now += seconds
        self.timeouts.poll()


@pytest.fixture(scope='module')
def qapp():
    # Constructing a Q(Core)Application calls setlocale(LC_ALL, ""), which would
    # localise strftime output (e.g. %B) for every test that runs after this one.
    saved = locale.setlocale(locale.LC_ALL)
    app = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.close()


@pytest.fixture
def sms(monkeypatch):
    sent = []
    monkeypatch.setattr(payment_module, 'send_operator_alert', sent.append)
    return sent


@pytest.fixture
def kiosk(qapp, db, sms, monkeypatch):
    monkeypatch.setenv('SIM_MODE', 'true')
    monkeypatch.setattr(payment_module, 'DatabaseManager', lambda *a, **k: db)
    monkeypatch.setattr(payment_module, 'log_error', db.log_error)
    acceptors = FakeAcceptors()
    monkeypatch.setattr(payment_module, 'get_persistent_gpio', lambda: acceptors)
    monkeypatch.setattr(hm, 'SIM_COIN_SECONDS', 0)
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())
    main_app = FakeMainApp()
    main_app.acceptors = acceptors
    model = PaymentModel(main_app)
    main_app.payment_screen.model = model
    model.change_dispenser.simulated = True
    yield main_app, model
    model.on_leave()


def stock_hoppers(db, ones, fives):
    db.update_cash_inventory(denomination=1, count=ones, type='coin')
    db.update_cash_inventory(denomination=5, count=fives, type='coin')


def fail_hopper_after(model, monkeypatch, denomination, n):
    dispenser = model.change_dispenser
    real = dispenser._dispense_coin
    count = {'n': 0}

    def coin(denom):
        if denom == denomination:
            count['n'] += 1
            if count['n'] > n:
                return False
        return real(denom)
    monkeypatch.setattr(dispenser, '_dispense_coin', coin)


def wait_for(condition, what):
    deadline = time.time() + 10
    while not condition():
        assert time.time() < deadline, f"timed out waiting for {what}"
        QApplication.processEvents()
        time.sleep(0.01)


def pay(main_app, model, change):
    """print_options -> payment -> auto-complete -> dispense, as on the kiosk.
    Returns once the voucher or thank-you screen is showing."""
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    payment_data['source'] = 'usb'  # what PrintOptionsController adds

    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(int(payment_data['total_cost'] + change))
    wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")
    return payment_data


def displayed(main_app):
    """What the voucher screen is showing right now (None if it isn't)."""
    if main_app.screens[-1] != 'voucher':
        return None
    view = main_app.voucher_screen.view
    return SimpleNamespace(
        title=view.title_label.text(),
        code=view.code_label.text(),
        code_visible=not view.code_row.isHidden(),
        qr=main_app.voucher_screen.model.qr_bytes,
    )


def finish(main_app, model):
    """Customer taps "I've saved it" if the voucher screen is up; the print succeeds."""
    if main_app.screens[-1] == 'voucher':
        main_app.voucher_screen.view.continue_button.click()
    assert main_app.screens[-1] == 'thank_you'
    record_print_success(model.db_manager, model.payment_ref)  # main_app does this once the print succeeds


def pay_with_change(main_app, model, change):
    payment_data = pay(main_app, model, change)
    shown = displayed(main_app)
    finish(main_app, model)
    return payment_data, shown


def logged_row(db):
    rows = db.get_transaction_history()
    assert len(rows) == 1
    return rows[0]


def test_reentering_payment_credits_each_coin_once(kiosk):
    """The acceptor service outlives the payment screen; re-entering must not
    connect its signals again (each extra connection credited every coin again)."""
    main_app, model = kiosk
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    model.set_payment_data(options.get_payment_data())
    for _ in range(3):
        model.on_enter()
        model.on_leave()
    model.on_enter()
    main_app.acceptors.coin_inserted.emit(1)
    assert model.amount_received == 1


def test_back_is_ignored_while_change_is_dispensing(kiosk, db, monkeypatch):
    """Back mid-payout used to stop the hoppers and log the paid job as cancelled."""
    main_app, model = kiosk
    stock_hoppers(db, ones=20, fives=20)
    monkeypatch.setattr(hm, 'SIM_COIN_SECONDS', 0.2)
    locked = []
    model.payment_locked.connect(locked.append)
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(int(payment_data['total_cost'] + 3))
    wait_for(lambda: model.dispense_thread and model.dispense_thread.isRunning(), "change to start")

    assert model.is_busy()
    model.go_back()
    wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")

    assert model.change_dispensed == {1: 3, 5: 0}
    assert [r['status'] for r in db.get_transaction_history()] == ['paid']  # settled, not cancelled
    assert locked[0] is True                   # Back/Vouchers greyed out from auto-complete


def test_inserted_money_restarts_the_payment_timeout(kiosk):
    """Only taps restarted it, so a customer still feeding money had the screen
    time out under them (a bill takes seconds to validate)."""
    from screens.payment.controller import PaymentController
    main_app, model = kiosk
    screen = PaymentController(main_app)
    main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    screen.set_payment_data(options.get_payment_data())
    screen.on_enter()
    try:
        main_app.timeouts.enter('payment', screen.timeout_policy())
        main_app.advance_time(59)
        assert main_app.timeouts.seconds_left() == 1
        screen.model.persistent_gpio.coin_inserted.emit(1)
        assert main_app.timeouts.seconds_left() == 60
    finally:
        screen.on_leave()


class TestCheckedVouchersAtPayment:
    """Vouchers checked in the balance popup are listed on payment with their balance and a
    tap-to-apply button. They are never applied by themselves (docs/remaining-work.md 2.2)."""

    @staticmethod
    def payment_screen(main_app):
        from screens.payment.controller import PaymentController
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        options = PrintOptionsModel()
        options.set_color_mode("Black and White")
        options.set_pdf_data({'path': PDF}, [1])
        screen.set_payment_data(options.get_payment_data())
        screen.on_enter()
        return screen

    @staticmethod
    def remember(main_app, code, remaining):
        main_app.session_vouchers.add(vm.normalize_code(code), remaining)

    def test_nothing_is_listed_when_nothing_was_checked(self, kiosk, db):
        main_app, model = kiosk
        screen = self.payment_screen(main_app)
        try:
            assert screen.view.checked_vouchers_box.isHidden()
        finally:
            screen.on_leave()

    def test_a_checked_voucher_is_listed_with_its_balance_but_not_applied(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        self.remember(main_app, code, 2)
        screen = self.payment_screen(main_app)
        try:
            assert not screen.view.checked_vouchers_box.isHidden()
            [button] = screen.view.checked_vouchers.values()
            assert "P2" in button.text() and code.replace("-", "")[:4] not in button.text()
            assert screen.model.applied_vouchers == []                       # never automatic
            assert VoucherManager(db).balance(code).remaining == 2
        finally:
            screen.on_leave()

    def test_tapping_it_applies_it_and_takes_it_off_the_list(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        self.remember(main_app, code, 2)
        screen = self.payment_screen(main_app)
        try:
            [button] = screen.view.checked_vouchers.values()
            button.click()

            [applied] = screen.model.applied_vouchers
            assert (applied.amount, applied.remaining) == (2, 0)
            assert screen.model.amount_owed == job_cost() - 2
            assert screen.view.checked_vouchers_box.isHidden()
        finally:
            screen.on_leave()

    def test_each_checked_voucher_gets_its_own_button(self, kiosk, db):
        main_app, model = kiosk
        first = issue_voucher(main_app, model, db, 1)
        second = issue_voucher(main_app, model, db, 3)
        self.remember(main_app, first, 1)
        self.remember(main_app, second, 3)
        screen = self.payment_screen(main_app)
        try:
            assert len(screen.view.checked_vouchers) == 2
            screen.view.checked_vouchers[vm.normalize_code(second)].click()
            assert [v.amount for v in screen.model.applied_vouchers] == [3]
            assert list(screen.view.checked_vouchers) == [vm.normalize_code(first)]   # the other stays
        finally:
            screen.on_leave()

    def test_a_voucher_applied_by_typing_leaves_the_list_too(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        self.remember(main_app, code, 2)
        screen = self.payment_screen(main_app)
        try:
            assert screen.apply_voucher_code(code)
            assert screen.view.checked_vouchers_box.isHidden()
        finally:
            screen.on_leave()

    def test_a_voucher_that_stopped_working_is_refused_and_stays_listed(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        self.remember(main_app, code, 2)
        VoucherManager(db).apply([code], 2)          # used up elsewhere since it was checked
        screen = self.payment_screen(main_app)
        try:
            [button] = screen.view.checked_vouchers.values()
            button.click()
            assert screen.model.applied_vouchers == []
            assert not screen.view.voucher_banner.isHidden()
        finally:
            screen.on_leave()


class TestChangeActuallyDispensed:
    def test_full_change_is_recorded_with_no_shortfall(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)

        pay_with_change(main_app, model, 13)

        row = logged_row(db)
        assert (row['change_given'], row['change_dispensed'], row['voucher_issued']) == (13, 13, 0)
        assert model.outcome.cause is None
        assert main_app.screens == ['thank_you']

    def test_hopper_failure_after_n_coins_records_what_came_out(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 1, 1)

        pay_with_change(main_app, model, 8)  # one ₱5 + one ₱1 come out, the second ₱1 jams

        row = logged_row(db)
        assert row['change_given'] == 8
        assert row['change_dispensed'] == 6
        assert row['change_given'] - row['change_dispensed'] == 2
        assert model.outcome.cause is ShortfallCause.HOPPER_FAILURE

    def test_low_inventory_is_a_predicted_shortfall(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)

        pay_with_change(main_app, model, 10)

        row = logged_row(db)
        assert (row['change_given'], row['change_dispensed']) == (10, 3)
        assert model.outcome.cause is ShortfallCause.PREDICTED

    def test_revenue_is_still_the_job_price(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        payment_data, _ = pay_with_change(main_app, model, 10)

        summary = {r['source']: r for r in db.get_accounting_summary()}
        assert summary['usb']['revenue'] == payment_data['total_cost']


def voucher_rows(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM vouchers")]
    finally:
        conn.close()


class TestVoucherForShortfall:
    def test_short_hoppers_issue_a_voucher_for_exactly_the_shortfall(self, kiosk, db, sms):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)

        _, shown = pay_with_change(main_app, model, 10)

        assert main_app.screens == ['voucher', 'thank_you']
        assert shown.code_visible
        [voucher] = voucher_rows(db.db_path)
        assert (voucher['initial_value'], voucher['remaining_value']) == (7, 7)
        issued_at = datetime.fromisoformat(voucher['created_at'])
        assert datetime.fromisoformat(voucher['expires_at']) == issued_at + timedelta(days=30)
        row = logged_row(db)
        assert (row['change_dispensed'], row['voucher_issued']) == (3, 7)
        assert voucher['payment_ref'] == row['payment_ref']

        balance = VoucherManager(db).balance(shown.code)
        assert (balance.success, balance.remaining) == (True, 7)
        assert sms == []  # predicted Shortfall: no operator alert

    def test_qr_payload_is_the_tagged_code_without_a_hyphen(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        _, shown = pay_with_change(main_app, model, 4)

        assert shown.qr == ("V1:" + shown.code.replace("-", "")).encode()
        assert len(shown.code.replace("-", "")) == 8

    def test_voucher_value_is_the_shortfall_not_the_change(self, kiosk, db, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 5, 1)  # one ₱5, then the ₱5 hopper jams
        statuses = []
        model.payment_status_updated.connect(statuses.append)

        pay_with_change(main_app, model, 11)  # ₱5 + six ₱1 top-up => all ₱11 comes out

        assert voucher_rows(db.db_path) == []
        assert logged_row(db)['change_dispensed'] == 11
        assert not any(s.startswith("Change dispensing failed") for s in statuses)  # all change came out

    def test_hopper_failure_shortfall_alerts_the_operator(self, kiosk, db, sms, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        fail_hopper_after(model, monkeypatch, 1, 1)

        _, shown = pay_with_change(main_app, model, 8)

        assert voucher_rows(db.db_path)[0]['initial_value'] == 2
        assert len(sms) == 1
        assert "hopper" in sms[0].lower() and "P2" in sms[0]
        assert shown.code.replace("-", "") not in sms[0]

    def test_full_change_sends_no_alert_and_shows_no_voucher(self, kiosk, db, sms):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)

        pay_with_change(main_app, model, 13)

        assert sms == []
        assert main_app.screens == ['thank_you']


class TestVoucherSaveFailure:
    def test_shows_no_code_logs_and_alerts(self, kiosk, db, sms, monkeypatch):
        main_app, model = kiosk
        stock_hoppers(db, ones=3, fives=0)
        monkeypatch.setattr(db, 'create_voucher', lambda **kwargs: False)

        _, shown = pay_with_change(main_app, model, 10)

        assert not shown.code_visible and shown.code == ""
        assert shown.qr is None
        assert "couldn't issue" in shown.title.lower()
        assert voucher_rows(db.db_path) == []
        assert [e['error_type'] for e in db.get_error_log()] == ["Voucher Issue Failed"]
        assert len(sms) == 1 and "P7" in sms[0]
        assert logged_row(db)['voucher_issued'] == 0


class TestVoucherScreenTiming:
    def test_shows_a_three_minute_countdown(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)

        pay(main_app, model, 4)

        assert main_app.timeouts.current_screen == 'voucher'
        assert main_app.timeouts.seconds_left() == 180
        # fixed: taps don't restart it and there is no "Still there?" prompt
        main_app.advance_time(100)
        main_app.timeouts.note_tap()
        assert main_app.timeouts.seconds_left() == 80
        assert not main_app.timeouts.warning_visible
        finish(main_app, model)

    def test_timeout_continues_to_thank_you_and_keeps_the_voucher(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)
        pay(main_app, model, 4)
        code = main_app.voucher_screen.view.code_label.text()

        main_app.advance_time(180)  # the 3 minutes are up
        wait_for(lambda: main_app.screens[-1] == 'thank_you', "the voucher screen to time out")

        assert main_app.voucher_screen.view.code_label.text() == ""  # code wiped on leave
        assert VoucherManager(db).balance(code).remaining == 4


# ---- Applying Vouchers at payment ------------------------------------------

def job(source='usb'):
    """payment_data for a 1-page B&W job, as PrintOptionsController builds it."""
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    payment_data = options.get_payment_data()
    payment_data['source'] = source
    return payment_data


def job_cost():
    return int(job()['total_cost'])


def start_payment(model, source='usb'):
    model.set_payment_data(job(source))
    model.on_enter()


def issue_voucher(main_app, model, db, value):
    """A real Voucher worth `value`, issued by overpaying with empty hoppers.
    Leaves the kiosk ready for the next customer; returns the shown code."""
    stock_hoppers(db, ones=0, fives=0)
    _, shown = pay_with_change(main_app, model, value)
    assert shown.code_visible
    main_app.screens.clear()
    return shown.code


def finish_with_cash(main_app, model, amount):
    if amount:
        main_app.acceptors.bill_inserted.emit(amount)
    wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")
    finish(main_app, model)


def row_for(db, payment_ref):
    [row] = [r for r in db.get_transaction_history() if r['payment_ref'] == payment_ref]
    return row


def applications(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM voucher_applications ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture
def messages(kiosk):
    _, model = kiosk
    seen = []
    model.voucher_message.connect(lambda message, is_error: seen.append((message, is_error)))
    return seen


class TestApplyVoucherAtPayment:
    @pytest.mark.parametrize('source', ['usb', 'wifi', 'email', 'scanner'])
    def test_issued_voucher_plus_cash_end_to_end(self, kiosk, db, source):
        main_app, model = kiosk
        cost = job_cost()
        assert cost > 2
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model, source)
        assert model.apply_voucher(code)
        assert model.amount_owed == cost - 2
        stock_hoppers(db, ones=20, fives=20)
        finish_with_cash(main_app, model, cost - 2)

        assert main_app.screens == ['thank_you']  # exact payment: no change, no new voucher
        ref = model.payment_ref
        row = row_for(db, ref)
        assert (row['voucher_applied'], row['amount_paid'], row['change_given']) == (2, cost - 2, 0)
        assert row['source'] == source
        [link] = applications(db.db_path)
        assert (link['amount'], link['payment_ref']) == (2, ref)
        assert voucher_rows(db.db_path)[0]['remaining_value'] == 0
        assert VoucherManager(db).balance(code).status == vm.LookupStatus.USED

    def test_vouchers_covering_the_cost_need_no_cash(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, cost + 2)

        start_payment(model)
        assert model.apply_voucher("V1:" + code.replace("-", ""))  # the QR payload form
        assert [(v.amount, v.remaining) for v in model.applied_vouchers] == [(cost, 2)]
        finish_with_cash(main_app, model, 0)

        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['amount_paid'], row['change_given']) == (cost, 0, 0)
        assert VoucherManager(db).balance(code).remaining == 2

    def test_several_vouchers_are_used_in_order_and_only_the_last_is_partial(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        first = issue_voucher(main_app, model, db, cost - 1)
        second = issue_voucher(main_app, model, db, 5)

        start_payment(model)
        assert model.apply_voucher(first)
        assert model.apply_voucher(second)
        assert [(v.amount, v.remaining) for v in model.applied_vouchers] == [(cost - 1, 0), (1, 4)]
        finish_with_cash(main_app, model, 0)

        assert [a['amount'] for a in applications(db.db_path)] == [cost - 1, 1]
        assert row_for(db, model.payment_ref)['voucher_applied'] == cost
        assert VoucherManager(db).balance(first).status == vm.LookupStatus.USED
        assert VoucherManager(db).balance(second).remaining == 4

    def test_overpaying_with_voucher_and_cash_gives_change_and_vouchers_the_shortfall(self, kiosk, db):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        model.apply_voucher(code)
        stock_hoppers(db, ones=2, fives=0)  # can give ₱2 of the ₱7 change
        main_app.acceptors.bill_inserted.emit(cost - 2 + 7)
        wait_for(lambda: 'voucher' in main_app.screens, "the new voucher")
        new_code = displayed(main_app).code
        finish(main_app, model)

        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['change_given'], row['change_dispensed'], row['voucher_issued']) \
            == (2, 7, 2, 5)
        assert VoucherManager(db).balance(new_code).remaining == 5

    def test_cancelling_leaves_the_voucher_untouched(self, kiosk, db):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        model.apply_voucher(code)
        model.go_back()

        assert model.applied_vouchers == []
        assert applications(db.db_path) == []
        assert VoucherManager(db).balance(code).remaining == 2

    def test_same_voucher_twice_is_applied_once(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)

        start_payment(model)
        assert model.apply_voucher(code)
        assert not model.apply_voucher(code.lower())
        assert model.voucher_total == 2
        assert "already applied" in messages[-1][0]

    def test_failed_apply_takes_nothing_and_lets_the_customer_pay_cash(self, kiosk, db, messages, monkeypatch):
        main_app, model = kiosk
        cost = job_cost()
        code = issue_voucher(main_app, model, db, 2)
        stock_hoppers(db, ones=20, fives=20)

        start_payment(model)
        model.apply_voucher(code)
        monkeypatch.setattr(db, 'apply_vouchers', lambda *a: False)
        main_app.acceptors.bill_inserted.emit(cost - 2)
        wait_for(lambda: messages[-1][1], "the apply failure")

        assert main_app.screens == []
        assert model.payment_ready and model.applied_vouchers == []
        assert "pay the rest in cash" in messages[-1][0]
        assert VoucherManager(db).balance(code).remaining == 2
        finish_with_cash(main_app, model, 2)
        row = row_for(db, model.payment_ref)
        assert (row['voucher_applied'], row['amount_paid']) == (0, cost)


class TestVoucherEntryMessages:
    def test_expired_used_and_unknown_codes_get_distinct_messages(self, kiosk, db, messages):
        import sqlite3
        main_app, model = kiosk
        expired = issue_voucher(main_app, model, db, 2)
        conn = sqlite3.connect(db.db_path)
        conn.execute("UPDATE vouchers SET expires_at = ?", (datetime.now() - timedelta(days=1),))
        conn.commit()
        conn.close()
        used = issue_voucher(main_app, model, db, job_cost())
        start_payment(model)
        model.apply_voucher(used)
        finish_with_cash(main_app, model, 0)
        main_app.screens.clear()

        start_payment(model)
        messages.clear()
        for code in (expired, used, "ZZZZ-ZZZZ"):
            assert not model.apply_voucher(code)
        texts = [m for m, _ in messages]
        assert all(is_error for _, is_error in messages)
        assert "expired" in texts[0]
        assert "fully used" in texts[1]
        assert texts[2] == vm.MSG_UNKNOWN
        assert len(set(texts)) == 3
        assert not any("redeem" in t.lower() for t in texts)

    def test_wrong_codes_lock_entry_and_show_the_cooldown(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        start_payment(model)

        for _ in range(vm.MAX_FAILED_ATTEMPTS):
            model.apply_voucher("ZZZZ-ZZZZ")
        assert "locked for 5 more minute" in messages[-1][0]
        assert not model.apply_voucher(code)  # even the right code, until the cooldown ends
        assert "locked" in messages[-1][0]
        assert model.applied_vouchers == []

    def test_malformed_entry_does_not_count_toward_the_lockout(self, kiosk, db, messages):
        main_app, model = kiosk
        start_payment(model)
        for _ in range(vm.MAX_FAILED_ATTEMPTS + 1):
            model.apply_voucher("hello")
        assert all("locked" not in m for m, _ in messages)

    def test_wrong_codes_read_count_toward_the_same_lockout(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        start_payment(model)

        for _ in range(vm.MAX_FAILED_ATTEMPTS - 1):
            model.apply_voucher("ZZZZ-ZZZZ")
        assert "locked" not in messages[-1][0]
        model.apply_voucher("V1:ZZZZZZZZ")  # a QR read of a wrong code
        assert "locked for 5 more minute" in messages[-1][0]
        assert not model.apply_voucher("V1:" + code.replace("-", ""))
        assert model.applied_vouchers == []

    def test_malformed_reads_do_not_count_toward_the_lockout(self, kiosk, db, messages):
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        start_payment(model)
        for _ in range(vm.MAX_FAILED_ATTEMPTS + 1):
            model.apply_voucher("V1:HELLO")
        assert all("locked" not in m for m, _ in messages)
        assert model.apply_voucher("V1:" + code.replace("-", ""))


class TestVoucherEntryOnScreen:
    def test_typed_code_is_applied_and_listed_with_what_is_left(self, kiosk, db):
        from screens.payment.controller import PaymentController
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        view = screen.view
        try:
            assert view.voucher_input.isHidden()
            view.use_voucher_btn.click()
            assert not view.voucher_input.isHidden()
            view.voucher_input.setText(code.lower())
            view.apply_voucher_btn.click()

            assert view.voucher_input.text() == ""  # the code isn't left on screen
            assert view.vouchers_label.text() == f"Voucher ••••-{code[-4:]}: P2 applied, P0 left"
            assert code not in view.vouchers_label.text()
            assert screen.model.amount_owed == job_cost() - 2
            assert "Use a voucher" == view.use_voucher_btn.text()
        finally:
            screen.on_leave()

    def test_code_typed_on_the_keypad_is_applied(self, kiosk, db):
        from screens.payment.controller import PaymentController
        from ui.widgets import BACKSPACE_KEY
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        view = screen.view
        try:
            assert view.voucher_keypad.isHidden()
            view.use_voucher_btn.click()
            assert not view.voucher_keypad.isHidden()
            # Every code character has a key; a slip is fixed with backspace.
            assert set(view.voucher_keypad.key_buttons) == set(vm.CODE_ALPHABET) | {BACKSPACE_KEY}
            keys = view.voucher_keypad.key_buttons
            chars = code.replace("-", "")  # no hyphen key: it's optional when typing
            keys[chars[0]].click()
            keys["Z" if chars[1] != "Z" else "Y"].click()
            keys[BACKSPACE_KEY].click()
            for ch in chars[1:]:
                keys[ch].click()
            assert view.voucher_input.text() == chars
            view.apply_voucher_btn.click()

            assert view.vouchers_label.text() == f"Voucher ••••-{code[-4:]}: P2 applied, P0 left"
            assert screen.model.amount_owed == job_cost() - 2
        finally:
            screen.on_leave()

    def test_qr_read_is_applied_without_opening_the_entry(self, kiosk, db):
        from screens.payment.controller import PaymentController
        main_app, model = kiosk
        code = issue_voucher(main_app, model, db, 2)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        view = screen.view
        try:
            assert screen.apply_voucher_code("V1:" + code.replace("-", ""))  # what main_app hands a Voucher read
            assert not view.voucher_banner.isHidden()
            assert view.voucher_banner._label.text() == "Voucher applied: P2 off. P0 left on this voucher."
            assert view.vouchers_label.text() == f"Voucher ••••-{code[-4:]}: P2 applied, P0 left"
            assert screen.model.amount_owed == job_cost() - 2
        finally:
            screen.on_leave()

    def test_several_qr_reads_are_applied_in_the_order_read(self, kiosk, db):
        from screens.payment.controller import PaymentController
        main_app, model = kiosk
        cost = job_cost()
        first = issue_voucher(main_app, model, db, cost - 1)
        second = issue_voucher(main_app, model, db, 5)
        screen = PaymentController(main_app)
        main_app.stacked_widget = SimpleNamespace(currentWidget=lambda: screen)
        screen.set_payment_data(job())
        screen.on_enter()
        try:
            for code in (first, second):
                assert screen.apply_voucher_code("V1:" + code.replace("-", ""))
            assert [(v.amount, v.remaining) for v in screen.model.applied_vouchers] == [(cost - 1, 0), (1, 4)]
            assert screen.model.amount_owed == 0
        finally:
            screen.on_leave()


class TestDashboardReflectsVouchers:
    """Issue #28 / #21's parent acceptance test: a Voucher issued for a real
    Shortfall, then Applied on a later payment, shows up on the Admin
    Dashboard's /accounting/data at each step."""

    @pytest.fixture
    def dashboard(self, db):
        from fastapi.testclient import TestClient
        from SSP.admin_dashboard.main import app
        from admin_dashboard.cli import create_account
        from admin_dashboard.dependencies import get_db

        create_account(db, "operator1", "s3cret!", "operator")
        app.dependency_overrides[get_db] = lambda: db
        try:
            client = TestClient(app)
            client.post("/login", json={"username": "operator1", "password": "s3cret!"})
            yield lambda: client.get("/accounting/data?range=today").json()
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_issue_then_apply_end_to_end(self, kiosk, db, dashboard):
        main_app, model = kiosk
        cost = job_cost()

        # Overpay by ₱10 with only ₱3 in the hoppers: ₱7 Shortfall -> Voucher.
        stock_hoppers(db, ones=3, fives=0)
        _, shown = pay_with_change(main_app, model, 10)
        row = logged_row(db)
        assert (row['change_dispensed'], row['voucher_issued']) == (3, 7)
        assert dashboard()["vouchers"] == {
            "change_dispensed": 3, "voucher_issued": 7, "voucher_applied": 0, "liability": 7}

        # A later payment Applies it; any cost left is paid in cash.
        main_app.screens.clear()
        start_payment(model)
        assert model.apply_voucher(shown.code)
        applied = min(7, cost)
        stock_hoppers(db, ones=20, fives=20)
        finish_with_cash(main_app, model, cost - applied)

        assert row_for(db, model.payment_ref)['voucher_applied'] == applied
        after = dashboard()
        assert after["vouchers"] == {
            "change_dispensed": 3, "voucher_issued": 7, "voucher_applied": applied,
            "liability": 7 - applied}
        assert [a['amount'] for a in applications(db.db_path)] == [applied]
        usb = {r["source"]: r for r in after["sources"]}["usb"]
        assert (usb["revenue"], usb["transaction_count"]) == (2 * cost, 2)


# ---- Cash put in for a payment that wasn't completed --------------------------

PRICE = 50  # dearer than the test PDF's ₱3, so cash can go in without paying in full


def start_priced_payment(model, total_cost=PRICE):
    payment_data = job()
    payment_data['total_cost'] = total_cost  # e.g. more pages or copies
    model.set_payment_data(payment_data)
    model.on_enter()


def leave_payment(main_app, model, to):
    """The customer leaves the payment screen without paying in full: Back goes to
    print options (PaymentController._go_back), a timeout anywhere else."""
    if to == 'printing_options':
        model.go_back()
    else:
        model.on_leave()  # what PaymentController._on_timeout does before show_screen
    main_app.show_screen(to)


class TestCarriedCredit:
    def test_back_keeps_the_cash_for_when_payment_reopens(self, kiosk, db):
        main_app, model = kiosk
        start_priced_payment(model)
        main_app.acceptors.coin_inserted.emit(5)

        leave_payment(main_app, model, 'printing_options')
        assert main_app.screens == ['printing_options']
        assert db.get_transaction_history() == []  # nothing recorded as cancelled

        start_priced_payment(model, 60)  # options changed, payment reopens
        assert model.amount_received == 5
        assert model.amount_owed == 55
        stock_hoppers(db, ones=20, fives=20)
        finish_with_cash(main_app, model, 55)

        row = row_for(db, model.payment_ref)
        assert (row['status'], row['amount_paid'], row['change_given']) == ('completed', 60, 0)
        assert voucher_rows(db.db_path) == []

    def test_carried_cash_covering_a_cheaper_job_completes_with_change(self, kiosk, db):
        main_app, model = kiosk
        start_priced_payment(model)
        main_app.acceptors.bill_inserted.emit(20)
        leave_payment(main_app, model, 'printing_options')

        stock_hoppers(db, ones=20, fives=20)
        main_app.show_screen('payment')
        start_priced_payment(model, 13)  # e.g. fewer pages: already paid for
        wait_for(lambda: {'voucher', 'thank_you'} & set(main_app.screens), "payment to finish")
        finish(main_app, model)

        row = row_for(db, model.payment_ref)
        assert (row['amount_paid'], row['change_given'], row['change_dispensed']) == (20, 7, 7)

    def test_leaving_print_options_turns_the_cash_into_a_voucher(self, kiosk, db):
        main_app, model = kiosk
        start_priced_payment(model)
        main_app.acceptors.coin_inserted.emit(5)
        main_app.acceptors.bill_inserted.emit(20)
        leave_payment(main_app, model, 'printing_options')

        main_app.show_screen('homepage')

        assert main_app.screens[-1] == 'voucher'
        shown = displayed(main_app)
        assert shown.title == "Here's your voucher" and shown.code_visible
        assert VoucherManager(db).balance(shown.code).remaining == 25
        [row] = db.get_transaction_history()
        assert (row['status'], row['amount_paid'], row['voucher_issued'], row['change_given']) \
            == ('cancelled_partial_payment', 25, 25, 0)
        inventory = {(i['type'], i['denomination']): i['count'] for i in db.get_cash_inventory()}
        assert inventory[('coin', 5)] >= 1 and inventory[('bill', 20)] >= 1

        main_app.voucher_screen.view.continue_button.click()
        assert main_app.screens[-1] == 'homepage'  # where they were going; nothing printed
        assert 'thank_you' not in main_app.screens
        assert model.carried_credit is None

    def test_payment_timeout_turns_the_cash_into_a_voucher(self, kiosk, db):
        main_app, model = kiosk
        start_priced_payment(model)
        main_app.acceptors.bill_inserted.emit(20)

        leave_payment(main_app, model, 'idle')

        assert main_app.screens == ['voucher']
        assert VoucherManager(db).balance(displayed(main_app).code).remaining == 20
        main_app.advance_time(180)  # nobody taps: it still moves on
        wait_for(lambda: main_app.screens[-1] == 'idle', "the voucher screen to time out")

    def test_the_voucher_can_pay_for_the_next_job(self, kiosk, db):
        main_app, model = kiosk
        start_priced_payment(model)
        main_app.acceptors.bill_inserted.emit(20)
        leave_payment(main_app, model, 'idle')
        code = displayed(main_app).code
        main_app.voucher_screen.view.continue_button.click()
        main_app.screens.clear()

        start_priced_payment(model, 30)
        assert model.apply_voucher(code)
        stock_hoppers(db, ones=20, fives=20)
        finish_with_cash(main_app, model, 10)
        assert row_for(db, model.payment_ref)['voucher_applied'] == 20

    def test_no_cash_in_means_no_voucher(self, kiosk, db):
        main_app, model = kiosk
        start_payment(model)
        leave_payment(main_app, model, 'printing_options')
        main_app.show_screen('homepage')
        assert main_app.screens == ['printing_options', 'homepage']
        assert db.get_transaction_history() == []

    def test_a_completed_payment_leaves_nothing_to_carry(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay_with_change(main_app, model, 3)
        model.on_leave()
        main_app.show_screen('idle')
        assert main_app.screens[-1] == 'idle'
        assert model.carried_credit is None
        assert voucher_rows(db.db_path) == []

    def test_vouchers_off_records_the_cash_without_a_voucher(self, kiosk, db):
        main_app, model = kiosk
        db.update_setting('vouchers_enabled', 0)
        start_priced_payment(model)
        main_app.acceptors.bill_inserted.emit(20)
        leave_payment(main_app, model, 'idle')

        assert main_app.screens == ['idle']
        [row] = db.get_transaction_history()
        assert (row['status'], row['amount_paid'], row['voucher_issued']) == ('cancelled_partial_payment', 20, 0)

    def test_voucher_save_failure_tells_the_customer_and_alerts(self, kiosk, db, sms, monkeypatch):
        main_app, model = kiosk
        monkeypatch.setattr(db, 'create_voucher', lambda **kwargs: False)
        start_priced_payment(model)
        main_app.acceptors.bill_inserted.emit(20)
        leave_payment(main_app, model, 'idle')

        shown = displayed(main_app)
        assert "couldn't issue" in shown.title.lower() and not shown.code_visible
        assert [e['error_type'] for e in db.get_error_log()] == ["Voucher Issue Failed"]
        assert len(sms) == 1 and "P20" in sms[0]
        assert db.get_transaction_history()[0]['voucher_issued'] == 0
        main_app.voucher_screen.view.continue_button.click()
        assert main_app.screens[-1] == 'idle'


# --- Scan digital copy: paid for before anything is delivered ---

@pytest.fixture
def scan(kiosk, db, tmp_path, monkeypatch):
    import shutil
    import screens.scan_destination.model as sdm
    monkeypatch.setattr(sdm, 'DatabaseManager', lambda *a, **k: db)
    monkeypatch.setenv('SCAN_UPLOAD_DIR', str(tmp_path / 'uploads'))
    stock_hoppers(db, ones=20, fives=20)
    scan_dir = tmp_path / 'scan_session'
    scan_dir.mkdir()
    pdf = str(scan_dir / 'scan.pdf')
    shutil.copy(PDF, pdf)
    destination = sdm.ScanDestinationModel()
    destination.set_scan_result(pdf, 1)
    main_app, model = kiosk
    return main_app, model, destination, scan_dir


def scan_print_plus_digital_data(fee):
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1], digital_fee=fee)
    payment_data = options.get_payment_data()
    payment_data['source'] = 'scanner'
    return payment_data


def test_digital_only_scan_pays_the_flat_fee_before_a_session_exists(scan, db):
    main_app, model, destination, scan_dir = scan
    db.update_setting('scan_digital_fee', 7)
    payment_data = destination.get_digital_only_payment_data()
    assert payment_data['total_cost'] == 7 and payment_data['print_job'] is False

    model.set_payment_data(payment_data)
    model.on_enter()
    assert model.is_print_job() is False
    assert main_app.scan_result_screen.session is None  # nothing delivered yet
    main_app.acceptors.bill_inserted.emit(20)
    wait_for(lambda: 'scan_result' in main_app.screens, "the OTP screen")

    assert main_app.screens[-1] == 'scan_result' and 'thank_you' not in main_app.screens
    assert main_app.scan_result_screen.session.otp
    assert main_app.scan_result_screen.then_print is False
    row = logged_row(db)
    assert (row['total_cost'], row['copies'], row['source']) == (7, 0, 'scanner')
    assert row['status'] == 'completed'
    assert revenue(db)['scanner'] == 7
    assert main_app.current_print_job is None
    assert not scan_dir.exists()  # the scan was copied for the session, then cleaned up


def test_scan_print_plus_digital_adds_the_fee_and_shows_the_otp_after_payment(scan, db):
    main_app, model, destination, scan_dir = scan
    options = PrintOptionsModel()
    options.set_color_mode("Black and White")
    options.set_pdf_data({'path': PDF}, [1])
    print_only = options.get_payment_data()
    options.set_pdf_data({'path': PDF}, [1], digital_fee=5)
    both = options.get_payment_data()
    assert both['total_cost'] == print_only['total_cost'] + 5
    both['source'] = 'scanner'

    model.set_payment_data(both)
    model.on_enter()
    assert main_app.scan_result_screen.session is None
    main_app.acceptors.bill_inserted.emit(int(both['total_cost']))
    wait_for(lambda: 'scan_result' in main_app.screens, "the OTP screen")

    assert main_app.scan_result_screen.session.otp
    assert main_app.scan_result_screen.then_print is True
    assert 'thank_you' not in main_app.screens  # the print starts after the OTP screen
    assert scan_dir.exists()                    # the print still needs the scan


def fail_digital_copies(monkeypatch):
    import managers.adapters.scan_adapter as adapter
    monkeypatch.setattr(adapter.ScanAdapter, 'handle_scan', lambda self, path, **k: (False, "disk full", None))


def test_failed_digital_only_copy_is_refunded_with_its_own_status(scan, db, monkeypatch):
    fail_digital_copies(monkeypatch)
    main_app, model, destination, _ = scan
    model.set_payment_data(destination.get_digital_only_payment_data())
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(5)
    wait_for(lambda: 'voucher' in main_app.screens, "the refund voucher")

    assert main_app.scan_result_screen.session is None
    assert main_app.voucher_screen.model.reason == 'digital_refund'
    assert "digital copy" in main_app.voucher_screen.model.body()
    main_app.voucher_screen.view.continue_button.click()
    assert main_app.screens[-1] == 'homepage'
    row = logged_row(db)
    assert row['status'] == 'digital_failed'
    assert row['voucher_issued'] == 5
    assert row['error_message'] == "disk full"
    assert sum(revenue(db).values()) == 0  # refunded, so not revenue
    totals = db.get_change_and_voucher_totals()
    assert totals['voucher_issued'] == 5


def test_failed_digital_copy_with_a_print_stays_paid_for_the_print_outcome(scan, db, monkeypatch):
    fail_digital_copies(monkeypatch)
    main_app, model, _, _ = scan
    payment_data = scan_print_plus_digital_data(fee=5)
    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(int(payment_data['total_cost']))
    wait_for(lambda: 'voucher' in main_app.screens, "the digital refund voucher")

    assert main_app.voucher_screen.model.reason == 'digital_refund'
    row = logged_row(db)
    assert row['status'] == 'paid'  # the print outcome settles it
    assert row['voucher_issued'] == 5
    assert main_app.current_print_job['digital_fee_refunded'] == 5


def test_failed_print_after_a_failed_digital_copy_does_not_refund_the_fee_twice(scan, db, monkeypatch):
    fail_digital_copies(monkeypatch)
    main_app, model, _, _ = scan
    payment_data = scan_print_plus_digital_data(fee=5)
    total = int(payment_data['total_cost'])
    model.set_payment_data(payment_data)
    model.on_enter()
    main_app.acceptors.bill_inserted.emit(total)
    wait_for(lambda: 'voucher' in main_app.screens, "the digital refund voucher")
    ref = logged_row(db)['payment_ref']

    outcome = refund_failed_print(db, ref, "jam",
                                  already_refunded=main_app.current_print_job['digital_fee_refunded'])

    assert outcome.voucher.value == total - 5
    row = logged_row(db)
    assert row['status'] == 'print_failed'
    assert row['voucher_issued'] == total  # the fee once, the print once
    assert db.get_voucher_liability(datetime.now()) == total


def test_failed_print_refund_keeps_the_shortfall_voucher_separate(kiosk, db):
    """already_refunded only trims the refund; it never touches the change Voucher."""
    main_app, model = kiosk
    stock_hoppers(db, ones=0, fives=0)
    payment_data = pay(main_app, model, 10)  # P10 shortfall voucher
    cost = int(payment_data['total_cost'])

    outcome = refund_failed_print(db, model.payment_ref, "jam", already_refunded=cost + 100)

    assert outcome.voucher is None and not outcome.voucher_failed  # nothing left to refund
    assert logged_row(db)['voucher_issued'] == 10


def test_digital_fee_defaults_to_env_and_admin_overrides_it(db, monkeypatch):
    from managers.digital_fee import get_digital_fee, set_digital_fee
    monkeypatch.setenv('SCAN_DIGITAL_FEE', '10')
    assert get_digital_fee(db) == 10
    set_digital_fee(db, 3)
    assert get_digital_fee(db) == 3
    set_digital_fee(db, -4)
    assert get_digital_fee(db) == 0


def revenue(db):
    return {r['source']: r['revenue'] for r in db.get_accounting_summary()}


class TestPrintOutcomeAfterSettlement:
    """Issue #59: the row is written when payment settles; the print outcome moves it on."""

    def test_settlement_logs_a_paid_row_and_updates_inventory_before_any_print_outcome(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)

        pay(main_app, model, 13)

        row = logged_row(db)
        assert row['status'] == 'paid'
        inv = {(i['denomination'], i['type']): i['count'] for i in db.get_cash_inventory()}
        assert (inv[(1, 'coin')], inv[(5, 'coin')]) == (20 - 3, 20 - 2)
        assert revenue(db) == {'usb': 0, 'wifi': 0, 'email': 0, 'scanner': 0}  # paid is not revenue yet

    def test_settlement_applies_once(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 13)
        model.settle_transaction()
        model.settle_transaction()
        assert len(db.get_transaction_history()) == 1
        inv = {(i['denomination'], i['type']): i['count'] for i in db.get_cash_inventory()}
        assert inv[(1, 'coin')] == 17

    def test_print_success_completes_the_row_and_counts_as_revenue(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        payment_data, _ = pay_with_change(main_app, model, 0)
        assert logged_row(db)['status'] == 'completed'
        assert revenue(db)['usb'] == payment_data['total_cost']

    def test_print_failure_refunds_one_voucher_and_is_not_revenue(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=0, fives=0)
        payment_data = pay(main_app, model, 10)  # P10 shortfall voucher
        ref = model.payment_ref
        cost = int(payment_data['total_cost'])

        outcome = refund_failed_print(db, ref, "Paper jam detected")

        row = logged_row(db)
        assert row['status'] == 'print_failed'
        assert outcome.voucher.value == cost
        assert row['voucher_issued'] == 10 + cost
        assert sum(revenue(db).values()) == 0
        totals = db.get_change_and_voucher_totals()
        assert totals['voucher_issued'] == 10 + cost
        assert totals['change_dispensed'] == 0
        assert db.get_voucher_liability(datetime.now()) == 10 + cost

    def test_refund_is_issued_at_most_once_per_payment(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 0)
        ref = model.payment_ref

        first = refund_failed_print(db, ref, "jam")
        second = refund_failed_print(db, ref, "jam again")

        assert first.applied and not second.applied
        assert len(voucher_rows(db.db_path)) == 1

    def test_a_failure_after_success_does_not_refund(self, kiosk, db):
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay_with_change(main_app, model, 0)

        assert not refund_failed_print(db, model.payment_ref, "late error").applied
        assert logged_row(db)['status'] == 'completed'

    def test_unsavable_refund_voucher_is_logged_alerted_and_row_still_written(self, kiosk, db, sms, monkeypatch):
        import managers.print_refund as pr
        main_app, model = kiosk
        stock_hoppers(db, ones=20, fives=20)
        pay(main_app, model, 0)
        monkeypatch.setattr(pr, 'send_operator_alert', sms.append)
        monkeypatch.setattr(db, 'create_voucher', lambda **kw: False)

        outcome = refund_failed_print(db, model.payment_ref, "jam")

        assert outcome.voucher is None and outcome.voucher_failed
        assert logged_row(db)['status'] == 'print_failed'
        assert len(sms) == 1
