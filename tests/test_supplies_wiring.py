"""
PrintingSystemApp's supply wiring (docs/remaining-work.md 2.5), called on a bare
stand-in for the app: a printer reporting its tray empty zeroes the paper count and
suppresses the generic print-failure SMS; the ink redirect fires only for a tank an
admin marked empty; and the low-ink SMS goes out once per tank.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from main_app import PrintingSystemApp  # noqa: E402

FULL = {'cyan': 100.0, 'magenta': 100.0, 'yellow': 100.0, 'black': 100.0}


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.conn.close()


def app_with(db, **extra):
    admin = SimpleNamespace(db_manager=db, model=MagicMock(), get_paper_count=lambda: 50)
    return SimpleNamespace(admin_screen=admin, _paper_empty_reported=False, **extra)


class TestPaperEmpty:
    def test_zeroes_the_count_and_remembers_it_for_the_failure(self, db):
        app = app_with(db)

        PrintingSystemApp.on_printer_paper_empty(app)

        app.admin_screen.model.mark_paper_empty.assert_called_once()
        assert app._paper_empty_reported is True

    def test_a_failure_to_zero_does_not_raise(self, db):
        app = app_with(db)
        app.admin_screen.model.mark_paper_empty.side_effect = RuntimeError("db locked")

        PrintingSystemApp.on_printer_paper_empty(app)  # must not raise

    def test_paper_out_failure_sends_no_second_sms(self, db, monkeypatch):
        sent = []
        monkeypatch.setattr('managers.sms_manager.send_printing_error_sms', sent.append)
        monkeypatch.setattr('utils.error_logger.log_error', lambda *a, **k: None)
        app = app_with(db, _refund_failed_print=lambda msg: True)
        app._paper_empty_reported = True

        PrintingSystemApp.on_print_failed(app, "No paper detected on HP_Smart_Tank")

        assert sent == []
        assert app._paper_empty_reported is False   # reset for the next failure

    def test_other_failures_still_send_the_sms(self, db, monkeypatch):
        sent = []
        monkeypatch.setattr('managers.sms_manager.send_printing_error_sms', sent.append)
        monkeypatch.setattr('utils.error_logger.log_error', lambda *a, **k: None)
        app = app_with(db, _refund_failed_print=lambda msg: True)

        PrintingSystemApp.on_print_failed(app, "Printer is offline")

        assert sent == ["Printer is offline"]


class TestInkBlocking:
    def test_low_ink_does_not_block(self, db):
        db.update_cmyk_ink_levels(2.0, 5.0, 10.0, 1.0)
        app = app_with(db)
        app._empty_ink_cartridges = lambda: PrintingSystemApp._empty_ink_cartridges(app)

        assert PrintingSystemApp.print_supplies_low(app) is False

    def test_a_tank_marked_empty_blocks(self, db):
        db.update_cmyk_ink_levels(100.0, 0.0, 100.0, 100.0)
        app = app_with(db)
        app._empty_ink_cartridges = lambda: PrintingSystemApp._empty_ink_cartridges(app)

        assert PrintingSystemApp.print_supplies_low(app) is True


class TestLowInkAlert:
    @pytest.fixture
    def sms(self, monkeypatch):
        sent = []
        monkeypatch.setattr('managers.sms_manager.send_operator_alert', sent.append)
        return sent

    def test_sends_once_per_tank_then_again_after_a_top_up(self, db, sms):
        app = app_with(db)

        PrintingSystemApp._alert_low_ink(app, {**FULL, 'cyan': 18.0})
        PrintingSystemApp._alert_low_ink(app, {**FULL, 'cyan': 15.0})
        assert len(sms) == 1 and "Cyan" in sms[0]

        PrintingSystemApp._alert_low_ink(app, {**FULL, 'cyan': 80.0})   # topped up: re-armed
        PrintingSystemApp._alert_low_ink(app, {**FULL, 'cyan': 19.0})
        assert len(sms) == 2

    def test_full_tanks_send_nothing(self, db, sms):
        PrintingSystemApp._alert_low_ink(app_with(db), FULL)
        assert sms == []

    def test_state_survives_in_the_settings_table(self, db, sms):
        PrintingSystemApp._alert_low_ink(app_with(db), {**FULL, 'black': 9.0})
        PrintingSystemApp._alert_low_ink(app_with(db), {**FULL, 'black': 7.0})   # a fresh app object
        assert len(sms) == 1
        assert db.get_setting('ink_low_alerted') == 'black'

    def test_a_failing_sms_never_raises(self, db, monkeypatch):
        def boom(_msg):
            raise OSError("modem unplugged")
        monkeypatch.setattr('managers.sms_manager.send_operator_alert', boom)

        PrintingSystemApp._alert_low_ink(app_with(db), {**FULL, 'black': 5.0})   # must not raise
