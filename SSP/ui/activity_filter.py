# ui/activity_filter.py
"""Tells the timeout manager that someone just touched the screen.

An application-wide event filter (like ui/tap_guard.py): any press anywhere counts, whichever
widget gets it, so no screen has to wire its own buttons to a timer. It never consumes the
event. Install it before the ScreenChangeTapGuard: Qt runs the last-installed filter first, so
the guard's dropped (doubled) taps never reach this one.
"""

from PyQt5.QtCore import QEvent, QObject

_PRESS_EVENTS = {QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.TouchBegin}


class ActivityFilter(QObject):
    def __init__(self, on_tap, parent=None):
        super().__init__(parent)
        self._on_tap = on_tap

    def eventFilter(self, obj, event):
        if event.type() in _PRESS_EVENTS:
            self._on_tap()
        return False
