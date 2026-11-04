"""
Low-change warnings (#24), driven through the real IdleController,
HomepageController and PaymentController (offscreen Qt) against a temp
SQLite DB whose cash_inventory rows are set below/above the warning threshold.

Only main_app is faked: a real QStackedWidget plus show_screen()'s
leave/enter lifecycle. The idle confirmation is a real modal dialog, answered
by clicking its button once it is showing.
"""
import locale
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QObject, QTimer, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox, QStackedWidget  # noqa: E402

import screens.homepage.model as homepage_module  # noqa: E402
import screens.idle.model as idle_module  # noqa: E402
import screens.payment.model as payment_module  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from managers.voucher_manager import MSG_UNGIVEN_CHANGE  # noqa: E402
from screens.homepage.controller import HomepageController  # noqa: E402
from screens.idle.controller import IdleController  # noqa: E402
from screens.payment.controller import PaymentController  # noqa: E402
from screens.print_options.model import PrintOptionsModel  # noqa: E402

PDF = os.path.join(os.path.dirname(__file__), '..', 'test_pdfs', 'Rootlocus-Plotting-1.pdf')


class FakeAcceptors(QObject):
    coin_inserted = pyqtSignal(int)
    bill_inserted = pyqtSignal(int)
    payment_status = pyqtSignal(str)

    def enable_payment(self):
        pass

    def disable_payment(self):
        pass

    def process_coin_timeout(self):
        pass


class Touch:
    """The mouse event the idle view's mousePressEvent passes on; only pos() is read."""

    def __init__(self, point):
        self._point = point

    def pos(self):
        return self._point


class FakeMainApp:
    """Just enough of PrintingSystemApp: a real stack and show_screen()'s lifecycle."""

    def __init__(self):
        self.stacked_widget = QStackedWidget()
        self.screens = []
        self.db_threader = None
        self.idle_screen = IdleController(self)
        self.homepage_screen = HomepageController(self)
        self._by_name = {'idle': self.idle_screen, 'homepage': self.homepage_screen}
        for widget in self._by_name.values():
            self.stacked_widget.addWidget(widget)

    def show_screen(self, name):
        current = self.stacked_widget.currentWidget()
        if self.screens and current is not None:
            current.on_leave()
        self.screens.append(name)
        widget = self._by_name.get(name)
        if widget is None:
            return  # usb/wifi/...: not part of these tests
        self.stacked_widget.setCurrentWidget(widget)
        widget.on_enter()

    def check_paper_count_and_redirect(self):
        return False

    def note_activity(self):
        pass

    def end_session(self):
        pass


@pytest.fixture(scope='module')
def qapp():
    # See test_payment_change_flow.py: QApplication() would localise strftime.
    saved = locale.setlocale(locale.LC_ALL)
    app = QApplication.instance() or QApplication([])
    locale.setlocale(locale.LC_ALL, saved)
    return app


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    manager = DatabaseManager(db_path=path)
    yield manager
    manager.close()


@pytest.fixture
def kiosk(qapp, db, monkeypatch):
    monkeypatch.setenv('SIM_MODE', 'true')
    for module in (idle_module, homepage_module):
        monkeypatch.setattr(module, 'DatabaseManager', lambda *a, **k: db)
    main_app = FakeMainApp()
    # Laid out like the kiosk, so the Admin button isn't at (0, 0) where tap_idle() touches.
    main_app.stacked_widget.resize(1024, 600)
    main_app.stacked_widget.show()
    yield main_app
    main_app.homepage_screen.on_leave()
    main_app.stacked_widget.close()


def stock_hoppers(db, ones, fives):
    db.update_cash_inventory(denomination=1, count=ones, type='coin')
    db.update_cash_inventory(denomination=5, count=fives, type='coin')


def banner_shown(screen):
    return not screen.view.low_change_banner.isHidden()


def tap_idle(main_app, answer=None):
    """Touch the idle screen. If a confirmation dialog opens, click `answer` on it.
    Returns the dialog's text, or None if no dialog opened."""
    seen = []

    def respond():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            seen.append(dialog.text())
            [button] = [b for b in dialog.buttons() if b.text() == answer]
            button.click()

    QTimer.singleShot(0, respond)
    idle = main_app.idle_screen
    idle._handle_screen_touch(Touch(idle.view.rect().topLeft()))  # away from the Admin button
    QApplication.processEvents()  # drop the pending singleShot if no dialog consumed it
    return seen[0] if seen else None


class TestBanner:
    def test_shown_on_idle_and_homepage_when_change_is_low(self, kiosk, db):
        stock_hoppers(db, ones=4, fives=3)  # ₱19 < ₱20

        kiosk.show_screen('idle')
        assert banner_shown(kiosk.idle_screen)
        kiosk.show_screen('homepage')
        assert banner_shown(kiosk.homepage_screen)

    def test_hidden_when_change_is_at_threshold(self, kiosk, db):
        stock_hoppers(db, ones=5, fives=3)  # ₱20, not below

        kiosk.show_screen('idle')
        assert not banner_shown(kiosk.idle_screen)
        kiosk.show_screen('homepage')
        assert not banner_shown(kiosk.homepage_screen)

    def test_clears_after_refill_on_next_enter(self, kiosk, db):
        stock_hoppers(db, ones=0, fives=0)
        kiosk.show_screen('idle')
        assert banner_shown(kiosk.idle_screen)

        stock_hoppers(db, ones=20, fives=20)  # as Kiosk Admin would
        kiosk.show_screen('homepage')
        assert not banner_shown(kiosk.homepage_screen)
        kiosk.show_screen('idle')
        assert not banner_shown(kiosk.idle_screen)

    def test_threshold_comes_from_settings(self, kiosk, db):
        stock_hoppers(db, ones=10, fives=5)  # ₱35
        kiosk.show_screen('idle')
        assert not banner_shown(kiosk.idle_screen)

        db.update_setting('low_change_warning_threshold', 50)
        kiosk.show_screen('homepage')
        assert banner_shown(kiosk.homepage_screen)

    def test_copy_says_voucher(self, kiosk, db):
        stock_hoppers(db, ones=0, fives=0)
        kiosk.show_screen('idle')
        text = kiosk.idle_screen.view.low_change_banner._label.text()
        assert 'Voucher' in text


class TestIdleConfirmation:
    def test_no_dialog_when_change_is_fine(self, kiosk, db):
        stock_hoppers(db, ones=20, fives=20)
        kiosk.show_screen('idle')

        assert tap_idle(kiosk) is None
        assert kiosk.screens[-1] == 'homepage'

    def test_continue_anyway_goes_to_homepage(self, kiosk, db):
        stock_hoppers(db, ones=0, fives=0)
        kiosk.show_screen('idle')

        text = tap_idle(kiosk, answer="Continue anyway")

        assert 'Voucher' in text
        assert kiosk.screens[-1] == 'homepage'

    def test_cancel_stays_on_idle(self, kiosk, db):
        stock_hoppers(db, ones=0, fives=0)
        kiosk.show_screen('idle')

        assert tap_idle(kiosk, answer="Cancel") is not None
        assert kiosk.screens == ['idle']


class TestPaymentCopy:
    @pytest.fixture
    def payment(self, qapp, db, monkeypatch):
        monkeypatch.setenv('SIM_MODE', 'true')
        monkeypatch.setattr(payment_module, 'DatabaseManager', lambda *a, **k: db)
        acceptors = FakeAcceptors()
        monkeypatch.setattr(payment_module, 'get_persistent_gpio', lambda: acceptors)
        controller = PaymentController(FakeMainApp())
        yield controller
        controller.on_leave()

    def test_keeps_per_job_message_and_mentions_vouchers(self, payment, db):
        stock_hoppers(db, ones=3, fives=1)
        options = PrintOptionsModel()
        options.set_color_mode("Black and White")
        options.set_pdf_data({'path': PDF}, [1])

        payment.model.set_payment_data(options.get_payment_data())
        payment.on_enter()

        text = payment.view.suggestion_banner._label.text()
        assert 'Max payment we can receive' in text
        assert MSG_UNGIVEN_CHANGE in text
