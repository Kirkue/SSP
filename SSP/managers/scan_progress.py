# managers/scan_progress.py
#
# Progress for a scan, estimated from how long recent scans took. eSCL sends the whole
# image only once the scan has finished, and there's no live preview, so the scanner never
# reports real progress: the screen paces a bar against the expected time instead.
# Measured on the kiosk (2026-10-30, docs/remaining-work.md 2.3): about 9 s for a Gray
# JPEG page and 20 s for Colour, which are the starting estimates.

from collections import deque

DEFAULT_SECONDS = {False: 9.0, True: 20.0}   # keyed by `colour`
# Never show a bar that has finished before the scan has: it waits at this until done.
PROGRESS_CAP = 0.95
HISTORY = 5


def progress_fraction(elapsed: float, expected: float) -> float:
    """How far along a scan looks, 0..PROGRESS_CAP, `elapsed` seconds into one expected to take `expected`."""
    if expected <= 0:
        return 0.0
    return max(0.0, min(PROGRESS_CAP, elapsed / expected))


class ScanTimeEstimator:
    """Remembers how long the last few scans of each kind took."""

    def __init__(self):
        self._recent = {False: deque(maxlen=HISTORY), True: deque(maxlen=HISTORY)}

    def record(self, colour: bool, seconds: float):
        if seconds > 0:
            self._recent[bool(colour)].append(seconds)

    def expected(self, colour: bool) -> float:
        """Average of the recent scans of this kind, else the measured default."""
        recent = self._recent[bool(colour)]
        if not recent:
            return DEFAULT_SECONDS[bool(colour)]
        return sum(recent) / len(recent)
