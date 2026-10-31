"""
Ink supply rules (docs/remaining-work.md 2.5): low ink only alerts the operator,
customers are blocked only when an admin marks a tank empty (0%), the estimate
never reaches 0 by itself, and the bottle yields come from .env.
"""
from unittest.mock import MagicMock

import pytest

from managers.ink_analysis_manager import InkAnalysisManager
from managers.ink_supply import (
    ESTIMATE_FLOOR, empty_cartridges, estimated_level_after, format_alerted,
    low_ink_alerts, low_ink_message, parse_alerted,
)

FULL = {'cyan': 100.0, 'magenta': 100.0, 'yellow': 100.0, 'black': 100.0}


class TestEmptyCartridges:
    def test_only_a_tank_at_zero_is_empty(self):
        assert empty_cartridges({**FULL, 'magenta': 0.0}) == {'magenta': 0.0}

    def test_low_is_not_empty(self):
        assert empty_cartridges({**FULL, 'black': 1.0, 'cyan': 5.0}) == {}

    def test_unknown_levels(self):
        assert empty_cartridges(None) == {}
        assert empty_cartridges({}) == {}


class TestEstimateNeverReachesZero:
    def test_stops_at_the_floor(self):
        assert estimated_level_after(5.0, 50.0) == ESTIMATE_FLOOR

    def test_normal_drain(self):
        assert estimated_level_after(80.0, 2.5) == pytest.approx(77.5)

    def test_a_tank_marked_empty_stays_empty(self):
        assert estimated_level_after(0.0, 3.0) == 0.0

    def test_a_tank_already_under_the_floor_is_left_alone(self):
        assert estimated_level_after(0.5, 3.0) == 0.5


class TestLowInkAlerts:
    def test_alerts_a_tank_once_it_reaches_the_threshold(self):
        to_alert, alerted = low_ink_alerts({**FULL, 'cyan': 20.0}, set(), 20.0)
        assert to_alert == {'cyan': 20.0}
        assert alerted == {'cyan'}

    def test_no_repeat_while_it_stays_low(self):
        to_alert, alerted = low_ink_alerts({**FULL, 'cyan': 12.0}, {'cyan'}, 20.0)
        assert to_alert == {}
        assert alerted == {'cyan'}

    def test_a_second_tank_alerts_without_repeating_the_first(self):
        to_alert, alerted = low_ink_alerts({**FULL, 'cyan': 12.0, 'black': 18.0}, {'cyan'}, 20.0)
        assert to_alert == {'black': 18.0}
        assert alerted == {'cyan', 'black'}

    def test_topping_up_rearms_the_alert(self):
        _, alerted = low_ink_alerts({**FULL, 'cyan': 70.0}, {'cyan'}, 20.0)
        assert alerted == set()
        to_alert, _ = low_ink_alerts({**FULL, 'cyan': 15.0}, alerted, 20.0)
        assert to_alert == {'cyan': 15.0}

    def test_all_full_alerts_nothing(self):
        assert low_ink_alerts(FULL, set(), 20.0) == ({}, set())


class TestAlertedSetting:
    def test_round_trip(self):
        assert parse_alerted(format_alerted({'black', 'cyan'})) == {'cyan', 'black'}

    @pytest.mark.parametrize("raw", [None, "", 0, "bogus"])
    def test_unusable_values_are_empty(self, raw):
        assert parse_alerted(raw) == set()

    def test_message_names_the_tanks(self):
        msg = low_ink_message({'cyan': 19.6, 'black': 8.0})
        assert "Cyan 20%" in msg and "Black 8%" in msg


class TestBottleYieldsFromConfig:
    def test_defaults_are_the_hp_data_sheet_yields(self, monkeypatch):
        from config import get_config
        monkeypatch.delenv('INK_YIELD_BLACK_PAGES', raising=False)
        monkeypatch.delenv('INK_YIELD_COLOR_PAGES', raising=False)
        assert get_config().ink_yield_black_pages == 6200
        assert get_config().ink_yield_color_pages == 9100

    def test_a_smaller_yield_drains_the_estimate_faster(self, monkeypatch):
        mgr = InkAnalysisManager()
        monkeypatch.setenv('INK_YIELD_BLACK_PAGES', '17000')
        monkeypatch.setenv('INK_YIELD_COLOR_PAGES', '17000')
        black_17k, color_17k = mgr._calculate_job_costs(5.0, 5.0, 0, 0, 10)

        monkeypatch.setenv('INK_YIELD_BLACK_PAGES', '8500')
        monkeypatch.setenv('INK_YIELD_COLOR_PAGES', '8500')
        black_8k, color_8k = mgr._calculate_job_costs(5.0, 5.0, 0, 0, 10)

        assert black_8k == pytest.approx(black_17k * 2)
        assert color_8k == pytest.approx(color_17k * 2)

    def test_threshold_default_and_override(self, monkeypatch):
        from config import get_config
        monkeypatch.delenv('INK_LOW_ALERT_PERCENT', raising=False)
        assert get_config().ink_low_alert_percent == 20.0
        monkeypatch.setenv('INK_LOW_ALERT_PERCENT', '15')
        assert get_config().ink_low_alert_percent == 15.0


class TestUpdateAfterPrintKeepsTheFloor:
    def _manager(self, levels):
        db = MagicMock()
        db.get_cmyk_ink_levels.return_value = levels
        db.update_cmyk_ink_levels.return_value = True
        return InkAnalysisManager(db_manager=db), db

    def test_a_huge_job_leaves_the_tank_at_the_floor_not_zero(self):
        mgr, db = self._manager({**FULL, 'black': 3.0})
        result = {'success': True, 'job_costs': {'black_cartridge_percent': 50.0, 'color_cartridge_percent': 0.0}}

        assert mgr.update_database_after_print(result, copies=1, color_mode="Black and White") is True

        cyan, magenta, yellow, black = db.update_cmyk_ink_levels.call_args[0]
        assert black == ESTIMATE_FLOOR
        assert (cyan, magenta, yellow) == (100.0, 100.0, 100.0)

    def test_colour_job_drains_all_four(self):
        mgr, db = self._manager(dict(FULL))
        result = {'success': True, 'job_costs': {'black_cartridge_percent': 1.0, 'color_cartridge_percent': 2.0}}

        mgr.update_database_after_print(result, copies=2, color_mode="Color")

        assert db.update_cmyk_ink_levels.call_args[0] == (96.0, 96.0, 96.0, 98.0)
