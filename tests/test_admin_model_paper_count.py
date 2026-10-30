"""
Tests that AdminModel's paper-count writes start from the database, not a
cached in-memory count. The DB is shared with the Admin Dashboard (ADR-0005):
a refill made there (e.g. POST /paper-reset) used to be silently overwritten
by the kiosk's next print, because decrement_paper_count subtracted from the
stale self.paper_count it loaded on screen entry.
"""
from unittest.mock import MagicMock, patch

import pytest

from database.db_manager import DatabaseManager
from database.models import init_db


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


@pytest.fixture
def model(db_path):
    from screens.admin import model as admin_model

    with patch.object(admin_model, "DatabaseManager", lambda: DatabaseManager(db_path=db_path)), \
            patch.object(admin_model, "get_sms_manager", lambda: MagicMock()):
        m = admin_model.AdminModel()
    return m


def _dashboard_sets_paper_count(db_path, count):
    """Writes through a separate connection, as the Admin Dashboard process does."""
    DatabaseManager(db_path=db_path).update_paper_count(count)


def _stored_paper_count(db_path):
    return DatabaseManager(db_path=db_path).get_setting('paper_count')


class TestPaperCountReadsDatabaseBeforeWriting:
    def test_print_after_remote_refill_decrements_from_refilled_count(self, model, db_path):
        _dashboard_sets_paper_count(db_path, 20)
        model.load_paper_count()

        _dashboard_sets_paper_count(db_path, 100)
        assert model.decrement_paper_count(5) is True

        assert _stored_paper_count(db_path) == 95

    def test_print_is_refused_when_remote_count_is_too_low(self, model, db_path):
        model.load_paper_count()  # cached as 100 (the default)

        _dashboard_sets_paper_count(db_path, 3)
        assert model.decrement_paper_count(5) is False

        assert _stored_paper_count(db_path) == 3

    def test_stepper_buttons_start_from_remote_count(self, model, db_path):
        model.load_paper_count()

        _dashboard_sets_paper_count(db_path, 40)
        model.increase_paper_count()
        assert _stored_paper_count(db_path) == 41

        _dashboard_sets_paper_count(db_path, 60)
        model.decrease_paper_count()
        assert _stored_paper_count(db_path) == 59


class TestLowPaperAlertThreshold:
    """One setting, LOW_PAPER_ALERT_SHEETS (default 10), decides the low-paper SMS."""

    def test_default_is_ten(self, monkeypatch):
        from config import get_config
        monkeypatch.delenv('LOW_PAPER_ALERT_SHEETS', raising=False)
        assert get_config().low_paper_alert_sheets == 10

    def test_env_overrides_it(self, monkeypatch):
        from config import get_config
        monkeypatch.setenv('LOW_PAPER_ALERT_SHEETS', '4')
        assert get_config().low_paper_alert_sheets == 4

    def test_alert_fires_at_the_configured_count(self, model, db_path, monkeypatch):
        monkeypatch.setenv('LOW_PAPER_ALERT_SHEETS', '20')
        model.sms_manager.send_custom_alert.return_value = True
        _dashboard_sets_paper_count(db_path, 25)
        model.load_paper_count()

        assert model.decrement_paper_count(4) is True   # 21: still above 20
        model.sms_manager.send_custom_alert.assert_not_called()

        assert model.decrement_paper_count(1) is True   # 20: at the threshold
        model.sms_manager.send_custom_alert.assert_called_once()

    def test_alert_is_sent_once_until_paper_is_refilled(self, model, db_path, monkeypatch):
        monkeypatch.setenv('LOW_PAPER_ALERT_SHEETS', '10')
        model.sms_manager.send_custom_alert.return_value = True
        _dashboard_sets_paper_count(db_path, 12)
        model.load_paper_count()

        model.decrement_paper_count(2)
        model.decrement_paper_count(1)
        assert model.sms_manager.send_custom_alert.call_count == 1


class TestMarkPaperEmpty:
    def test_zeroes_the_count_in_the_database(self, model, db_path):
        _dashboard_sets_paper_count(db_path, 40)
        model.load_paper_count()

        model.mark_paper_empty()

        assert _stored_paper_count(db_path) == 0
        assert model.paper_count == 0

    def test_sends_no_low_paper_sms(self, model, db_path):
        """The printer thread already sent the out-of-paper SMS."""
        model.sms_manager.send_custom_alert.return_value = True
        _dashboard_sets_paper_count(db_path, 40)
        model.load_paper_count()

        model.mark_paper_empty()
        model.check_low_paper_alert()

        model.sms_manager.send_custom_alert.assert_not_called()

    def test_refill_rearms_the_low_paper_alert(self, model, db_path):
        model.sms_manager.send_custom_alert.return_value = True
        model.mark_paper_empty()

        model.reset_paper_count()
        _dashboard_sets_paper_count(db_path, 9)
        model.load_paper_count()
        model.check_low_paper_alert()

        model.sms_manager.send_custom_alert.assert_called_once()
