"""
The single kiosk inactivity timeout (docs/remaining-work.md 2.1), driven by a fake clock:
one countdown shared by the timeout and the label, any activity restarts it, a "Still there?"
warning near the end that can add time, and busy screens that never time out.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication  # noqa: E402

from managers.timeout_manager import Event, TimeoutCore, TimeoutManager, TimeoutPolicy  # noqa: E402

app = QApplication.instance() or QApplication([])


class TestCore:
    def core(self, **kw):
        c = TimeoutCore(warning_seconds=15, extend_seconds=30)
        c.start("payment", TimeoutPolicy(seconds=60, **kw), now=0)
        return c

    def test_counts_down_from_the_policy(self):
        c = self.core()
        assert c.remaining(0) == 60
        assert c.remaining(45) == 15
        assert c.remaining(100) == 0          # never negative

    def test_nothing_happens_before_the_warning(self):
        assert self.core().poll(44.9) is Event.NONE

    def test_warns_once_at_the_warning_time(self):
        c = self.core()
        assert c.poll(45) is Event.WARN
        assert c.poll(46) is Event.NONE      # only once

    def test_expires_at_zero(self):
        c = self.core()
        c.poll(45)
        assert c.poll(60) is Event.EXPIRE

    def test_a_policy_without_warning_goes_straight_to_expiry(self):
        c = self.core(warn=False)
        assert c.poll(50) is Event.NONE
        assert c.poll(60) is Event.EXPIRE

    def test_no_policy_means_no_timeout(self):
        c = TimeoutCore()
        c.start("admin", None, now=0)
        assert not c.active
        assert c.remaining(1000) is None
        assert c.poll(1000) is Event.NONE

    def test_activity_restarts_the_full_time(self):
        c = self.core()
        assert c.note_activity(40) is False
        assert c.remaining(40) == 60

    def test_activity_after_a_warning_reports_that_it_cleared_it(self):
        c = self.core()
        c.poll(50)
        assert c.note_activity(52) is True
        assert c.poll(52 + 44) is Event.NONE          # the warning can come round again later
        assert c.poll(52 + 45) is Event.WARN

    def test_a_tap_counts_like_activity(self):
        c = self.core()
        c.note_tap(30)
        assert c.remaining(30) == 60

    def test_a_fixed_countdown_ignores_taps(self):
        c = self.core(taps_reset=False)
        c.note_tap(30)
        assert c.remaining(30) == 30

    def test_extend_adds_to_what_is_left(self):
        c = self.core()
        c.poll(50)                                     # warning showing, 10 s left
        c.extend(50)
        assert c.remaining(50) == 40                   # 10 + 30
        assert c.poll(50) is Event.NONE                # 40 s left is outside the 15 s window
        assert c.poll(75) is Event.WARN                # and it warns again at 15 s left

    def test_extend_after_the_deadline_adds_from_now(self):
        c = self.core()
        c.extend(100)
        assert c.remaining(100) == 30

    def test_busy_screen_never_expires_and_starts_over(self):
        busy = {"now": True}
        c = self.core(busy=lambda: busy["now"])
        assert c.poll(59) is Event.NONE
        assert c.poll(90) is Event.NONE                # long past the 60 s
        assert c.remaining(90) == 60                   # restarted, not stuck at zero
        busy["now"] = False
        assert c.poll(90 + 45) is Event.WARN
        assert c.poll(90 + 60) is Event.EXPIRE

    def test_busy_hides_the_warning_too(self):
        c = self.core(busy=lambda: True)
        assert c.poll(50) is Event.NONE
        assert not c.warned


class Harness:
    """A TimeoutManager on a fake clock, recording every signal."""

    def __init__(self, warning=15, extend=30):
        self.now = 1000.0
        self.manager = TimeoutManager(warning, extend, clock=lambda: self.now)
        self.ticks, self.warnings, self.hidden, self.expired = [], [], [], []
        self.manager.tick.connect(self.ticks.append)
        self.manager.warning_shown.connect(lambda s, m: self.warnings.append((s, m)))
        self.manager.warning_hidden.connect(lambda: self.hidden.append(True))
        self.manager.expired.connect(lambda name, action: self.expired.append((name, action)))

    def advance(self, seconds):
        self.now += seconds
        self.manager.poll()


@pytest.fixture
def h():
    harness = Harness()
    yield harness
    harness.manager._timer.stop()


class TestManager:
    def test_entering_a_screen_starts_the_label_at_the_full_time(self, h):
        h.manager.enter("homepage", TimeoutPolicy(seconds=60))
        assert h.ticks[-1] == 60
        assert h.manager.current_screen == "homepage"

    def test_the_label_follows_the_same_clock_as_the_timeout(self, h):
        h.manager.enter("homepage", TimeoutPolicy(seconds=60))
        h.advance(20)
        assert h.ticks[-1] == 40
        h.advance(40)
        assert h.expired == [("homepage", None)]
        assert h.ticks[-1] is None                      # label hidden at expiry

    def test_entering_a_screen_with_no_policy_hides_the_label(self, h):
        h.manager.enter("homepage", TimeoutPolicy(seconds=60))
        h.manager.enter("admin", None)
        assert h.ticks[-1] is None
        h.advance(1000)
        assert h.expired == []

    def test_the_old_screens_countdown_cannot_fire_on_the_new_screen(self, h):
        """Entering a screen starts a fresh countdown: nothing from the last one survives."""
        h.manager.enter("homepage", TimeoutPolicy(seconds=60))
        h.advance(55)
        h.manager.enter("usb", TimeoutPolicy(seconds=60))
        h.advance(10)
        assert h.expired == []
        assert h.ticks[-1] == 50

    def test_expiry_hands_over_the_screens_action(self, h):
        called = []
        h.manager.enter("payment", TimeoutPolicy(seconds=10, action=lambda: called.append(1), warn=False))
        h.advance(10)
        name, action = h.expired[0]
        assert name == "payment"
        action()
        assert called == [1]

    def test_warning_appears_with_seconds_left_and_the_screens_message(self, h):
        h.manager.enter("payment", TimeoutPolicy(seconds=60, warning_message=lambda: "Your P20 will be saved."))
        h.advance(45)
        assert h.warnings == [(15, "Your P20 will be saved.")]
        assert h.manager.warning_visible

    def test_a_failing_message_still_shows_the_warning(self, h):
        def boom():
            raise RuntimeError("db closed")
        h.manager.enter("payment", TimeoutPolicy(seconds=60, warning_message=boom))
        h.advance(45)
        assert h.warnings == [(15, "")]

    def test_extend_dismisses_the_warning_and_adds_time(self, h):
        h.manager.enter("payment", TimeoutPolicy(seconds=60))
        h.advance(50)
        h.manager.extend()
        assert not h.manager.warning_visible and h.hidden
        assert h.ticks[-1] == 40
        h.advance(40)
        assert h.expired and h.expired[0][0] == "payment"

    def test_expiring_with_the_warning_up_closes_it(self, h):
        h.manager.enter("payment", TimeoutPolicy(seconds=60))
        h.advance(45)
        h.advance(15)
        assert h.hidden and not h.manager.warning_visible
        assert len(h.expired) == 1

    def test_taps_restart_the_time(self, h):
        h.manager.enter("file_browser", TimeoutPolicy(seconds=60))
        h.advance(40)
        h.manager.note_tap()
        assert h.ticks[-1] == 60

    def test_taps_are_ignored_while_the_warning_is_up(self, h):
        h.manager.enter("payment", TimeoutPolicy(seconds=60))
        h.advance(50)
        h.manager.note_tap()
        assert h.manager.warning_visible
        assert h.manager.seconds_left() == 10

    def test_a_coin_while_the_warning_is_up_dismisses_it(self, h):
        h.manager.enter("payment", TimeoutPolicy(seconds=60))
        h.advance(50)
        h.manager.note_activity()
        assert not h.manager.warning_visible and h.hidden
        assert h.manager.seconds_left() == 60

    def test_activity_with_no_countdown_is_harmless(self, h):
        h.manager.note_activity()
        h.manager.note_tap()
        h.manager.extend()
        assert h.expired == []

    def test_busy_screen_does_not_expire_or_warn(self, h):
        busy = {"now": True}
        h.manager.enter("payment", TimeoutPolicy(seconds=60, busy=lambda: busy["now"]))
        for _ in range(10):
            h.advance(30)
        assert h.expired == [] and h.warnings == []
        busy["now"] = False
        h.advance(60)
        assert len(h.expired) == 1

    def test_expiry_stops_the_countdown(self, h):
        h.manager.enter("homepage", TimeoutPolicy(seconds=5, warn=False))
        h.advance(5)
        h.advance(100)
        assert len(h.expired) == 1                      # not a second time

    def test_warning_and_extension_come_from_the_settings(self):
        harness = Harness(warning=20, extend=45)
        try:
            harness.manager.enter("payment", TimeoutPolicy(seconds=60))
            harness.advance(40)
            assert harness.warnings == [(20, "")]
            harness.manager.extend()
            assert harness.manager.seconds_left() == 65     # 20 left + 45
            assert harness.manager.extend_seconds == 45
        finally:
            harness.manager._timer.stop()
