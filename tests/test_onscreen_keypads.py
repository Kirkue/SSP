"""
The touchscreen has no physical or OS keyboard, so every field a customer or
operator types into has an on-screen keypad: the wifi/email code screens'
phone-style keypad with Send, and Kiosk Admin's ink-level keypad.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QStackedWidget  # noqa: E402

from screens.admin.view import AdminScreenView  # noqa: E402
from screens.email.view import EmailScreenView  # noqa: E402
from screens.wifi.view import WifiScreenView  # noqa: E402
from ui.widgets import BACKSPACE_KEY, Card  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def press(view, keys):
    for key in keys:
        view.otp_entry.keypad.key_buttons[key].click()


@pytest.mark.parametrize("view_class", [WifiScreenView, EmailScreenView])
class TestCodeScreenKeypad:
    def test_offers_the_digits_and_backspace(self, qapp, view_class):
        view = view_class()
        assert set(view.otp_entry.keypad.key_buttons) == set("0123456789") | {BACKSPACE_KEY}

    def test_has_no_qr_scan_card(self, qapp, view_class):
        # The reader is always listening, so a "QR Code Scan" button did nothing
        assert view_class().findChildren(Card) == []

    def test_send_submits_the_typed_code(self, qapp, view_class):
        view = view_class()
        sent = []
        view.send_otp_clicked.connect(sent.append)
        press(view, "0123459")
        press(view, [BACKSPACE_KEY, "6"])
        view.send_button.click()
        assert sent == ["012346"]  # a leading 0 is kept

    def test_stops_at_six_digits(self, qapp, view_class):
        view = view_class()
        press(view, "1234567")
        assert view.otp_input.text() == "123456"

    def test_every_key_reports_activity(self, qapp, view_class):
        view = view_class()
        activity = MagicMock()
        view.otp_entry_activity.connect(activity)
        press(view, ["4", BACKSPACE_KEY])
        assert activity.call_count == 2

    def test_clear_otp_input_empties_the_field(self, qapp, view_class):
        view = view_class()
        press(view, "42")
        view.clear_otp_input()
        assert view.otp_input.text() == ""


@pytest.mark.parametrize("name", ["wifi", "email"])
def test_code_screens_time_out_to_idle_after_a_minute(qapp, name):
    """Typing counts as activity because it's taps, which main_app's app-wide filter sees
    (tests/test_timeout_manager.py); the screen itself only declares its policy."""
    import importlib
    model_module = importlib.import_module(f"screens.{name}.model")
    controller_module = importlib.import_module(f"screens.{name}.controller")
    main_app = MagicMock()
    with patch.object(model_module, "DatabaseManager", MagicMock):
        controller_class = getattr(controller_module, f"{name.capitalize()}Controller")
        screen = controller_class(main_app)

    policy = screen.timeout_policy()
    assert policy.seconds == 60 and policy.warn and policy.taps_reset

    policy.action()
    main_app.show_screen.assert_called_once_with('idle')


class TestAdminInkKeypad:
    @pytest.fixture
    def view(self, qapp):
        view = AdminScreenView()
        view.show()
        yield view
        view.close()

    def type_on(self, view, keys):
        for key in keys:
            view.ink_keypad.key_buttons[key].click()

    def test_types_into_the_focused_ink_field(self, qapp, view):
        view.update_cmyk_display(80.0, 70.0, 60.0, 50.0)
        view.magenta_input.setFocus()
        qapp.processEvents()
        self.type_on(view, [BACKSPACE_KEY] * 4 + list("42.5"))
        assert view.magenta_input.text() == "42.5"
        assert view.cyan_input.text() == "80.0"

    def test_types_nowhere_without_a_focused_ink_field(self, qapp, view):
        view.update_cmyk_display(80.0, 70.0, 60.0, 50.0)
        view.back_button.setFocus()
        qapp.processEvents()
        self.type_on(view, "9")
        texts = [f.text() for f in (view.cyan_input, view.magenta_input, view.yellow_input, view.black_input)]
        assert texts == ["80.0", "70.0", "60.0", "50.0"]

    def test_typed_levels_are_what_update_sends(self, qapp, view):
        view.cyan_input.setFocus()
        qapp.processEvents()
        self.type_on(view, "33")
        for field in (view.magenta_input, view.yellow_input, view.black_input):
            field.setText("10")
        sent = []
        view.update_cmyk_clicked.connect(lambda *levels: sent.append(levels))
        view._update_cmyk_levels()
        assert sent == [(33.0, 10.0, 10.0, 10.0)]
