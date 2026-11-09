"""Attempt limit for the touchscreen admin PIN dialog.

N consecutive wrong PINs lock the dialog for M minutes. The deadline is a
wall-clock timestamp in the `settings` table, so closing the dialog, recreating
the model or restarting the app never shortens or restarts it. The lock only
blocks PIN entry; no customer screen consults it.
"""
from datetime import datetime, timedelta

SETTING_FAILED = "pin_failed_attempts"
SETTING_LOCKED_UNTIL = "pin_locked_until"
ERROR_SOURCE = "PIN Dialog"


class PinLockout:
    def __init__(self, db, max_attempts=5, lockout_minutes=5, clock=datetime.now, on_lockout=None):
        self.db = db
        self.max_attempts = max(1, int(max_attempts))
        self.lockout = timedelta(minutes=lockout_minutes)
        self.clock = clock
        self.on_lockout = on_lockout

    def _locked_until(self):
        raw = self.db.get_setting(SETTING_LOCKED_UNTIL, "")
        try:
            return datetime.fromisoformat(str(raw)) if raw else None
        except ValueError:
            return None

    def _failed(self):
        try:
            return int(self.db.get_setting(SETTING_FAILED, 0))
        except (TypeError, ValueError):
            return 0

    def remaining(self):
        """Seconds of lockout left (0 when not locked)."""
        until = self._locked_until()
        if until is None:
            return 0
        return max(0, int((until - self.clock()).total_seconds() + 0.999))

    def is_locked(self):
        return self.remaining() > 0

    def record_success(self):
        if self._failed():
            self.db.update_setting(SETTING_FAILED, 0)

    def record_failure(self):
        """Count a wrong PIN; returns True if this one started a lockout."""
        failed = self._failed() + 1
        if failed < self.max_attempts:
            self.db.update_setting(SETTING_FAILED, failed)
            return False
        self.db.update_setting(SETTING_FAILED, 0)
        self.db.update_setting(SETTING_LOCKED_UNTIL, (self.clock() + self.lockout).isoformat())
        minutes = self.lockout.total_seconds() / 60
        message = f"PIN dialog locked for {minutes:g} min after {self.max_attempts} wrong PINs"
        try:
            self.db.log_error(ERROR_SOURCE, message, ERROR_SOURCE)
        except Exception as e:
            print(f"PIN lockout: could not log error: {e}")
        if self.on_lockout:
            try:
                self.on_lockout(message)
            except Exception as e:
                print(f"PIN lockout: alert failed: {e}")
        return True
