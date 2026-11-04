# managers/timeout_manager.py
#
# One inactivity timeout for the whole kiosk (docs/remaining-work.md 2.1). It replaces the
# 13 per-screen QTimers and the separate "Remaining Time" countdown, which could disagree
# (a screen restarted its own timer but not the label, or the other way round).
#
#   - main_app owns the single TimeoutManager. show_screen() hands it the new screen's
#     TimeoutPolicy (screens declare one with a `timeout_policy()` method; no policy means
#     no timeout and no label: idle, thank_you, admin, data_viewer).
#   - Any tap, and coin/bill/QR events, restart the countdown (note_activity / note_tap).
#   - With `warning_seconds` left a "Still there?" prompt offers `extend_seconds` more.
#   - The label and the timeout read the same deadline, so they can't drift apart.
#   - A screen that is busy (change dispensing, a scan running) never times out.
#
# TimeoutCore is plain Python driven by an injected clock, so it's unit-tested without Qt.

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

TICK_MS = 1000


@dataclass(frozen=True)
class TimeoutPolicy:
    """What a screen wants from the timeout.

    seconds         inactivity before `action` runs
    action          what to do on expiry (navigate, clean up); None does nothing
    busy            when it returns True the screen can't time out right now, and the
                    countdown starts over (e.g. payment while change is dispensing)
    warn            show the "Still there?" prompt near the end
    taps_reset      any tap restarts the countdown. False for a fixed countdown, e.g. the
                    voucher screen's 3 minutes to copy the code
    warning_message extra line for the prompt, e.g. what happens to cash already inserted
    """
    seconds: int = 60
    action: Optional[Callable[[], None]] = None
    busy: Optional[Callable[[], bool]] = None
    warn: bool = True
    taps_reset: bool = True
    warning_message: Optional[Callable[[], str]] = None


class Event(Enum):
    NONE = "none"
    WARN = "warn"
    EXPIRE = "expire"


class TimeoutCore:
    """The countdown for the current screen. All times come from the caller's clock."""

    def __init__(self, warning_seconds: int = 15, extend_seconds: int = 30):
        self.warning_seconds = warning_seconds
        self.extend_seconds = extend_seconds
        self.name: Optional[str] = None
        self.policy: Optional[TimeoutPolicy] = None
        self.deadline = 0.0
        self.warned = False

    @property
    def active(self) -> bool:
        return self.policy is not None

    def start(self, name: str, policy: Optional[TimeoutPolicy], now: float):
        """Begin a screen's countdown; a None policy means the screen has no timeout."""
        self.name = name if policy else None
        self.policy = policy
        self.deadline = now + policy.seconds if policy else 0.0
        self.warned = False

    def stop(self):
        self.name = None
        self.policy = None
        self.warned = False

    def remaining(self, now: float) -> Optional[float]:
        return max(0.0, self.deadline - now) if self.active else None

    def _restart(self, now: float) -> bool:
        """Back to the full time. True if that dismissed a visible warning."""
        was_warned = self.warned
        self.deadline = now + self.policy.seconds
        self.warned = False
        return was_warned

    def note_activity(self, now: float) -> bool:
        """Something happened that proves the customer is there (a coin, a QR read, ...)."""
        return self._restart(now) if self.active else False

    def note_tap(self, now: float) -> bool:
        """A tap: counts unless the screen has a fixed countdown."""
        return self._restart(now) if self.active and self.policy.taps_reset else False

    def extend(self, now: float):
        """The "Still there?" button: add time to what's left."""
        if not self.active:
            return
        self.deadline = max(self.deadline, now) + self.extend_seconds
        self.warned = False

    def poll(self, now: float) -> Event:
        if not self.active:
            return Event.NONE
        if self.policy.busy is not None and self.policy.busy():
            self._restart(now)
            return Event.NONE
        remaining = self.deadline - now
        if remaining <= 0:
            return Event.EXPIRE
        if self.policy.warn and not self.warned and remaining <= self.warning_seconds:
            self.warned = True
            return Event.WARN
        return Event.NONE


class TimeoutManager(QObject):
    """Qt wrapper: ticks the core once a second and reports what happened."""

    tick = pyqtSignal(object)                  # whole seconds left, or None when no countdown
    warning_shown = pyqtSignal(int, str)       # seconds left, extra message ("" if none)
    warning_hidden = pyqtSignal()
    expired = pyqtSignal(str, object)          # screen name, the policy's action

    def __init__(self, warning_seconds: int = 15, extend_seconds: int = 30,
                 clock: Callable[[], float] = time.monotonic, parent=None):
        super().__init__(parent)
        self.core = TimeoutCore(warning_seconds, extend_seconds)
        self._clock = clock
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.poll)
        self.warning_visible = False

    @property
    def extend_seconds(self) -> int:
        return self.core.extend_seconds

    @property
    def current_screen(self) -> Optional[str]:
        return self.core.name

    def enter(self, name: str, policy: Optional[TimeoutPolicy]):
        """The screen `name` is now showing, with its policy (None: no timeout)."""
        self._hide_warning()
        self.core.start(name, policy, self._clock())
        if policy is None:
            self._timer.stop()
            self.tick.emit(None)
            return
        self._timer.start()
        self._emit_tick()

    def leave(self):
        self.enter("", None)

    def note_activity(self):
        if self.core.note_activity(self._clock()):
            self._hide_warning()
        self._emit_tick()

    def note_tap(self):
        """A tap anywhere. While the warning is up it's modal, so taps don't count: only
        its own button does (extend)."""
        if self.warning_visible:
            return
        if self.core.note_tap(self._clock()):
            self._hide_warning()
        self._emit_tick()

    def extend(self):
        self.core.extend(self._clock())
        self._hide_warning()
        self._emit_tick()

    def seconds_left(self) -> Optional[int]:
        remaining = self.core.remaining(self._clock())
        return None if remaining is None else math.ceil(remaining)

    def poll(self):
        """One tick: update the label, raise the warning, or expire the screen."""
        event = self.core.poll(self._clock())
        if event is Event.EXPIRE:
            name, policy = self.core.name, self.core.policy
            self._hide_warning()
            self.core.stop()
            self._timer.stop()
            self.tick.emit(None)
            self.expired.emit(name, policy.action)
            return
        if event is Event.WARN:
            self.warning_visible = True
            message = ""
            if self.core.policy.warning_message is not None:
                try:
                    message = self.core.policy.warning_message() or ""
                except Exception as e:
                    print(f"⚠️ Timeout warning message failed: {e}")
            self.warning_shown.emit(self.seconds_left() or 0, message)
        self._emit_tick()

    def _emit_tick(self):
        self.tick.emit(self.seconds_left())

    def _hide_warning(self):
        if self.warning_visible:
            self.warning_visible = False
            self.warning_hidden.emit()
