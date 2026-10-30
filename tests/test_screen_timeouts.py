"""
How the single timeout (managers/timeout_manager.py) is wired in (docs/remaining-work.md 2.1):
which screens declare a timeout and where each sends the customer, what main_app does with
an expiry, the label, the "Still there?" overlay and the app-wide tap filter.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QWidget  # noqa: E402

from main_app import PrintingSystemApp  # noqa: E402
from managers.session_vouchers import SessionVouchers  # noqa: E402
from managers.timeout_manager import TimeoutManager, TimeoutPolicy  # noqa: E402
from screens.email import EmailController  # noqa: E402
from screens.file_browser import FileBrowserController  # noqa: E402
from screens.homepage import HomepageController  # noqa: E402
from screens.payment import PaymentController  # noqa: E402
from screens.print_options import PrintOptionsController  # noqa: E402
from screens.scan_destination import ScanDestinationController  # noqa: E402
from screens.scan_result import ScanResultController  # noqa: E402
from screens.scanner import ScannerController  # noqa: E402
from screens.usb import USBController  # noqa: E402
from screens.voucher import VoucherController  # noqa: E402
from screens.wifi import WifiController  # noqa: E402
from ui.activity_filter import ActivityFilter  # noqa: E402
from ui.timeout_warning import TimeoutWarning  # noqa: E402

app = QApplication.instance() or QApplication([])


def stand_in(**attrs):
    """A stand-in for a controller's `self`, with a recording main_app."""
    return SimpleNamespace(main_app=MagicMock(), **attrs)


class TestWhichScreensTimeOut:
    @pytest.mark.parametrize("controller", [
        HomepageController, USBController, WifiController, EmailController, ScannerController,
        FileBrowserController, PrintOptionsController, PaymentController, ScanDestinationController,
        ScanResultController, VoucherController,
    ])
    def test_customer_screens_declare_a_policy(self, controller):
        assert callable(getattr(controller, 'timeout_policy', None))

    def test_the_balance_popup_is_not_a_screen(self):
        from main_app import PrintingSystemApp as App
        assert 'voucher_balance' not in App.SCREEN_MAP

    @pytest.mark.parametrize("name", ["idle", "thank_you", "admin", "data_viewer"])
    def test_these_screens_have_no_timeout(self, name):
        """idle has nowhere to go, thank_you and voucher move on themselves, and an admin
        logs out by hand."""
        import importlib
        module = importlib.import_module(f"screens.{name}")
        controller = getattr(module, ''.join(p.capitalize() for p in name.split('_')) + "Controller")
        assert not hasattr(controller, 'timeout_policy')


class TestDestinations:
    """Before a file is chosen a timeout goes to idle; mid-flow it goes to the homepage."""

    def test_homepage_goes_to_idle(self):
        s = stand_in()
        HomepageController._on_timeout(s)
        s.main_app.show_screen.assert_called_once_with('idle')

    def test_usb_goes_to_idle(self):
        s = stand_in()
        USBController._on_timeout(s)
        s.main_app.show_screen.assert_called_once_with('idle')

    @pytest.mark.parametrize("controller", [WifiController, EmailController])
    def test_wifi_and_email_go_to_idle(self, controller):
        s = stand_in()
        controller._on_timeout(s)
        s.main_app.show_screen.assert_called_once_with('idle')

    def test_scanner_discards_its_pages_and_goes_to_idle(self):
        s = stand_in(model=MagicMock())
        ScannerController._on_timeout(s)
        s.model.cancel.assert_called_once()
        s.main_app.show_screen.assert_called_once_with('idle')

    @pytest.mark.parametrize("controller", [FileBrowserController, PrintOptionsController])
    def test_file_browser_and_print_options_clear_the_files_then_go_home(self, controller):
        s = stand_in()
        controller._on_timeout(s)
        names = [c[0] for c in s.main_app.method_calls]
        assert names == ['end_session', 'show_screen']
        s.main_app.show_screen.assert_called_once_with('homepage')

    def test_scan_destination_clears_its_pdf_then_goes_home(self):
        s = stand_in(_cleanup_pdf=MagicMock())
        ScanDestinationController._on_timeout(s)
        s._cleanup_pdf.assert_called_once()
        s.main_app.show_screen.assert_called_once_with('homepage')

    def test_payment_clears_files_and_goes_home_after_turning_the_acceptors_off(self):
        calls = []
        s = stand_in(model=SimpleNamespace(is_busy=lambda: False),
                     on_leave=lambda: calls.append('on_leave'),
                     _manual_disable_acceptors=lambda: calls.append('disable'))
        s.main_app.end_session.side_effect = lambda: calls.append('end_session')
        s.main_app.show_screen.side_effect = lambda n: calls.append(f'show:{n}')

        PaymentController._on_timeout(s)

        assert calls == ['on_leave', 'disable', 'end_session', 'show:homepage']

    def test_payment_never_leaves_while_change_is_dispensing(self):
        s = stand_in(model=SimpleNamespace(is_busy=lambda: True))
        PaymentController._on_timeout(s)
        s.main_app.show_screen.assert_not_called()


class TestPolicies:
    def test_payment_is_held_off_while_busy_and_warns_about_the_cash(self):
        model = SimpleNamespace(is_busy=lambda: True, amount_received=20)
        s = SimpleNamespace(model=model, _on_timeout=lambda: None)
        s._timeout_warning_message = lambda: PaymentController._timeout_warning_message(s)

        policy = PaymentController.timeout_policy(s)

        assert policy.seconds == 60 and policy.warn
        assert policy.busy() is True
        assert policy.warning_message() == "Your ₱20 will be saved as a voucher."

    def test_payment_warning_is_silent_with_no_cash_in(self):
        s = SimpleNamespace(model=SimpleNamespace(amount_received=0))
        assert PaymentController._timeout_warning_message(s) == ""

    def test_payment_warning_shows_whole_and_part_pesos_plainly(self):
        s = SimpleNamespace(model=SimpleNamespace(amount_received=7.5))
        assert "₱7.5" in PaymentController._timeout_warning_message(s)

    def test_scanner_never_times_out_under_a_running_scan(self):
        model = SimpleNamespace(is_busy=lambda: True)
        policy = ScannerController.timeout_policy(SimpleNamespace(model=model, _on_timeout=None))
        assert policy.busy() is True

    def test_homepage_holds_off_behind_the_pin_dialog(self):
        s = SimpleNamespace(_pin_dialog_open=True, _on_timeout=None)
        policy = HomepageController.timeout_policy(s)
        assert policy.busy() is True
        s._pin_dialog_open = False
        assert policy.busy() is False

    def test_voucher_is_a_fixed_three_minutes(self):
        policy = VoucherController.timeout_policy(SimpleNamespace(_continue=None))
        assert (policy.seconds, policy.warn, policy.taps_reset) == (180, False, False)

    def test_scan_result_is_a_fixed_minute_then_carries_on(self):
        policy = ScanResultController.timeout_policy(SimpleNamespace(_on_timeout=None))
        assert (policy.seconds, policy.warn, policy.taps_reset) == (60, False, False)

    def test_the_rest_are_a_minute_with_the_prompt(self):
        for controller in (HomepageController, USBController, FileBrowserController, PrintOptionsController,
                           ScanDestinationController, WifiController, EmailController):
            policy = controller.timeout_policy(SimpleNamespace(
                _on_timeout=None, _pin_dialog_open=False))
            assert (policy.seconds, policy.warn, policy.taps_reset) == (60, True, True), controller


def app_stand_in(current_name="homepage", widget=None):
    label = QLabel()
    return SimpleNamespace(
        timeouts=MagicMock(), global_timer_label=label, _place_timer_label=lambda: None,
        _current_screen_name=lambda: current_name,
        session_vouchers=SessionVouchers(),
        stacked_widget=SimpleNamespace(currentWidget=lambda: widget),
    )


class TestMainAppWiring:
    def test_entering_a_screen_hands_over_its_policy(self):
        policy = TimeoutPolicy(seconds=60)
        widget = SimpleNamespace(timeout_policy=lambda: policy)
        a = app_stand_in(widget=widget)

        PrintingSystemApp._enter_timeout(a, "homepage")

        a.timeouts.enter.assert_called_once_with("homepage", policy)

    def test_a_screen_without_a_policy_gets_none(self):
        a = app_stand_in(widget=SimpleNamespace())
        PrintingSystemApp._enter_timeout(a, "admin")
        a.timeouts.enter.assert_called_once_with("admin", None)

    def test_a_broken_policy_does_not_break_navigation(self):
        def boom():
            raise RuntimeError("model gone")
        a = app_stand_in(widget=SimpleNamespace(timeout_policy=boom))
        PrintingSystemApp._enter_timeout(a, "payment")
        a.timeouts.enter.assert_called_once_with("payment", None)

    def test_the_label_follows_the_countdown(self):
        a = app_stand_in()
        PrintingSystemApp._on_timeout_tick(a, 42)
        assert a.global_timer_label.text() == "Remaining Time: 42s"
        assert not a.global_timer_label.isHidden()

        PrintingSystemApp._on_timeout_tick(a, None)
        assert a.global_timer_label.isHidden()

    def test_expiry_runs_the_screens_action_if_it_is_still_showing(self):
        ran = []
        a = app_stand_in(current_name="payment")
        PrintingSystemApp._on_screen_timeout(a, "payment", lambda: ran.append(1))
        assert ran == [1]

    def test_a_stale_expiry_cannot_pull_the_customer_off_another_screen(self):
        """The bug class this replaces: a timeout from a screen the customer has already
        left must never navigate them away from the one they're on."""
        ran = []
        a = app_stand_in(current_name="file_browser")
        PrintingSystemApp._on_screen_timeout(a, "homepage", lambda: ran.append(1))
        assert ran == []

    def test_an_expiry_with_no_action_is_harmless(self):
        PrintingSystemApp._on_screen_timeout(app_stand_in(current_name="x"), "x", None)

    def test_activity_goes_to_the_manager(self):
        a = app_stand_in()
        PrintingSystemApp.note_activity(a)
        a.timeouts.note_activity.assert_called_once()

    def test_end_session_forgets_the_vouchers_the_customer_checked(self, monkeypatch):
        import managers.usb_file_manager as ufm
        monkeypatch.setattr(ufm, 'USBFileManager', lambda: MagicMock())
        a = app_stand_in()
        a.session_vouchers.add("ABCD1234", 7)
        PrintingSystemApp.end_session(a)
        assert len(a.session_vouchers) == 0

    def test_end_session_clears_temp_files_and_never_raises(self, monkeypatch):
        import managers.usb_file_manager as ufm
        cleared = []

        class Fake:
            def cleanup_all_temp_folders(self):
                cleared.append(1)
        monkeypatch.setattr(ufm, 'USBFileManager', Fake)
        PrintingSystemApp.end_session(app_stand_in())
        assert cleared == [1]

        def boom():
            raise OSError("disk gone")
        monkeypatch.setattr(ufm, 'USBFileManager', boom)
        PrintingSystemApp.end_session(app_stand_in())   # must not raise


class TestTimeoutWarningOverlay:
    @pytest.fixture
    def parent(self):
        w = QWidget()
        w.resize(800, 600)
        w.show()
        yield w
        w.close()

    def test_hidden_until_a_warning(self, parent):
        overlay = TimeoutWarning(30, parent)
        assert overlay.isHidden()

    def test_shows_the_countdown_and_the_cash_message(self, parent):
        overlay = TimeoutWarning(30, parent)
        overlay.show_warning(12, "Your ₱20 will be saved as a voucher.")
        assert not overlay.isHidden()
        assert "12" in overlay.countdown_label.text()
        assert overlay.message_label.text() == "Your ₱20 will be saved as a voucher."
        assert not overlay.message_label.isHidden()

    def test_no_message_line_when_there_is_nothing_to_say(self, parent):
        overlay = TimeoutWarning(30, parent)
        overlay.show_warning(15, "")
        assert overlay.message_label.isHidden()

    def test_covers_the_whole_window_so_nothing_underneath_can_be_tapped(self, parent):
        overlay = TimeoutWarning(30, parent)
        overlay.show_warning(15)
        assert overlay.geometry() == parent.rect()

    def test_button_names_the_extension_and_emits(self, parent):
        overlay = TimeoutWarning(45, parent)
        assert "45" in overlay.extend_button.text()
        clicks = []
        overlay.extend_clicked.connect(lambda: clicks.append(1))
        overlay.extend_button.click()
        assert clicks == [1]

    def test_updates_and_hides(self, parent):
        overlay = TimeoutWarning(30, parent)
        overlay.show_warning(15)
        overlay.update_remaining(9)
        assert "9" in overlay.countdown_label.text()
        overlay.update_remaining(None)           # a None tick leaves it alone
        assert "9" in overlay.countdown_label.text()
        overlay.hide_warning()
        assert overlay.isHidden()


class TestActivityFilter:
    @pytest.fixture
    def taps(self):
        taps = []
        activity_filter = ActivityFilter(lambda: taps.append(1))
        app.installEventFilter(activity_filter)
        widget = QWidget()
        widget.resize(200, 100)
        widget.show()
        yield taps, widget
        widget.close()
        app.removeEventFilter(activity_filter)

    def test_a_tap_anywhere_counts(self, taps):
        counted, widget = taps
        QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(10, 10))
        assert counted == [1]

    def test_keys_and_moves_do_not_count(self, taps):
        counted, widget = taps
        QTest.keyClick(widget, Qt.Key_A)
        QTest.mouseMove(widget, QPoint(20, 20))
        assert counted == []

    def test_it_never_swallows_the_tap(self, taps):
        counted, widget = taps
        button = QPushButton("Go", widget)
        button.resize(80, 40)
        button.show()
        clicked = []
        button.clicked.connect(lambda: clicked.append(1))
        QTest.mouseClick(button, Qt.LeftButton)
        assert clicked == [1] and counted


class TestManagerWithTheOverlay:
    def test_the_prompt_is_modal_so_a_tap_does_not_dismiss_it_but_its_button_extends(self):
        now = {"t": 0.0}
        manager = TimeoutManager(15, 30, clock=lambda: now["t"])
        overlay = TimeoutWarning(30)
        manager.warning_shown.connect(overlay.show_warning)
        manager.warning_hidden.connect(overlay.hide_warning)
        overlay.extend_clicked.connect(manager.extend)
        try:
            manager.enter("payment", TimeoutPolicy(seconds=60, warning_message=lambda: "Your ₱5 will be saved as a voucher."))
            now["t"] = 50
            manager.poll()
            assert not overlay.isHidden() and manager.warning_visible

            manager.note_tap()                           # a stray tap
            assert not overlay.isHidden()

            overlay.extend_button.click()                # the button
            assert overlay.isHidden() and not manager.warning_visible
            assert manager.seconds_left() == 40
        finally:
            manager._timer.stop()
