"""PIN dialog attempt limit (issue #98): pure model tests on a temp SQLite file
and a fake clock — no dialog shown, no modem."""
from datetime import datetime, timedelta

import pytest
from PyQt5.QtWidgets import QApplication

from database.db_manager import DatabaseManager
from database.models import init_db
from managers.pin_lockout import PinLockout
from screens.dialogs.pin_dialog.model import PinDialogModel


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(tmp_path):
    path = str(tmp_path / "t.db")
    init_db(path)
    clock = Clock()
    alerts = []
    dbs = []

    def make_model():
        db = DatabaseManager(db_path=path)
        dbs.append(db)
        lockout = PinLockout(db, 5, 5, clock=clock, on_lockout=alerts.append)
        m = PinDialogModel(lockout=lockout)
        m.CORRECT_PIN = "4321"
        return m

    yield make_model, clock, alerts, path
    for d in dbs:
        d.close()


def enter(m, pin):
    m.clear_pin()
    for d in pin:
        m.add_digit(d)
    return m.validate_pin()


def wrong(m, n):
    for _ in range(n):
        assert enter(m, "0000") is False


def test_fifth_wrong_pin_locks(env):
    make, _, alerts, _ = env
    m = make()
    wrong(m, 4)
    assert not m.is_locked()
    wrong(m, 1)
    assert m.is_locked()
    assert len(alerts) == 1


def test_correct_pin_resets_counter(env):
    make, _, _, _ = env
    m = make()
    wrong(m, 4)
    assert enter(m, "4321") is True
    wrong(m, 4)
    assert not m.is_locked()


def test_locked_rejects_correct_pin_and_blocks_digits(env):
    make, _, _, _ = env
    m = make()
    wrong(m, 5)
    assert enter(m, "4321") is False
    assert m.get_current_pin() == ""


def test_expires_after_lockout_minutes(env):
    make, clock, _, _ = env
    m = make()
    wrong(m, 5)
    clock.advance(minutes=4, seconds=59)
    assert m.is_locked()
    clock.advance(seconds=1)
    assert not m.is_locked()
    assert enter(m, "4321") is True


def test_counter_resets_when_lockout_starts(env):
    make, clock, _, _ = env
    m = make()
    wrong(m, 5)
    clock.advance(minutes=5)
    wrong(m, 4)
    assert not m.is_locked()
    wrong(m, 1)
    assert m.is_locked()


def test_recreating_model_keeps_lockout_and_counter(env):
    make, clock, _, _ = env
    wrong(make(), 5)
    m2 = make()
    assert m2.is_locked()
    assert m2.lockout.remaining() == 300
    clock.advance(minutes=5)
    wrong(make(), 3)
    wrong(make(), 2)
    assert make().is_locked()


def test_error_logged_once_per_lockout(env):
    make, _, _, path = env
    m = make()
    wrong(m, 5)
    enter(m, "0000")  # while locked: not counted
    rows = [r for r in DatabaseManager(db_path=path).get_error_log() if "PIN Dialog" in str(r)]
    assert len(rows) == 1


def test_remaining_signal(env):
    make, _, _, _ = env
    m = make()
    seen = []
    m.lock_changed.connect(lambda locked, s: seen.append((locked, s)))
    wrong(m, 5)
    assert seen[-1] == (True, 300)


def test_alert_failure_never_disturbs(env):
    make, clock, _, path = env
    db = DatabaseManager(db_path=path)

    def boom(_):
        raise RuntimeError("modem")
    lo = PinLockout(db, 2, 1, clock=clock, on_lockout=boom)
    lo.record_failure()
    assert lo.record_failure() is True
    assert lo.is_locked()
    db.close()
