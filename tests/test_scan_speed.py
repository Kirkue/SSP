"""
Scan speed (docs/remaining-work.md 2.3), measured on the kiosk: Gray + JPEG is ~9 s a
page against ~20 s for Color + PNG, and the scanner answers "Device busy" for ~2.6 s after
a scan. So: Gray + JPEG by default with Colour on request, a retry on busy, and a progress
bar paced by how long recent scans took.
"""
import os
import subprocess
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

import managers.scanner as scanner_mod  # noqa: E402

app = QApplication.instance() or QApplication([])
from managers.scan_progress import (  # noqa: E402
    DEFAULT_SECONDS, PROGRESS_CAP, ScanTimeEstimator, progress_fraction,
)
from managers.scanner import SaneAirscanScanner, ScannerError, SimScanner  # noqa: E402
from managers.scanner_manager import ScannerManager  # noqa: E402

DEVICE = "escl:http://localhost:60000"
BUSY = b"scanimage: sane_start: Device busy"


class FakeScanimage:
    """Stands in for subprocess.run: fails with `failures` in turn, then writes an image."""

    def __init__(self, failures=()):
        self.failures = list(failures)
        self.commands = []

    def __call__(self, command, stdout=None, **kwargs):
        self.commands.append(command)
        if self.failures:
            raise subprocess.CalledProcessError(1, command, stderr=self.failures.pop(0))
        stdout.write(b"\xff\xd8fake jpeg")
        return SimpleNamespace(returncode=0)


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(scanner_mod.time, 'sleep', lambda s: None)


class TestScanimageCommand:
    def test_default_is_gray_jpeg(self, monkeypatch):
        fake = FakeScanimage()
        monkeypatch.setattr(subprocess, 'run', fake)

        path = SaneAirscanScanner(DEVICE, timeout=60).scan_page(200)

        command = fake.commands[0]
        assert "--format=jpeg" in command
        assert "--mode=Gray" in command
        assert command[command.index("--resolution") + 1] == "200"
        assert path.endswith(".jpg") and os.path.getsize(path) > 0
        os.remove(path)

    def test_colour_on_request(self, monkeypatch):
        fake = FakeScanimage()
        monkeypatch.setattr(subprocess, 'run', fake)

        path = SaneAirscanScanner(DEVICE, timeout=60).scan_page(200, colour=True)

        assert "--mode=Color" in fake.commands[0]
        os.remove(path)


class TestDeviceBusyRetry:
    def test_retries_while_busy_then_succeeds(self, monkeypatch, no_sleep):
        fake = FakeScanimage(failures=[BUSY, BUSY])
        monkeypatch.setattr(subprocess, 'run', fake)

        path = SaneAirscanScanner(DEVICE, timeout=60).scan_page(200)

        assert len(fake.commands) == 3
        assert os.path.getsize(path) > 0
        os.remove(path)

    def test_gives_up_when_the_scanner_stays_busy(self, monkeypatch, no_sleep):
        fake = FakeScanimage(failures=[BUSY] * 50)
        monkeypatch.setattr(subprocess, 'run', fake)
        monkeypatch.setattr(scanner_mod, 'BUSY_RETRY_SECONDS', 0)

        with pytest.raises(ScannerError, match="busy"):
            SaneAirscanScanner(DEVICE, timeout=60).scan_page(200)
        assert len(fake.commands) == 1

    def test_a_busy_giveup_leaves_no_temp_file(self, monkeypatch, no_sleep, tmp_path):
        monkeypatch.setattr(subprocess, 'run', FakeScanimage(failures=[BUSY] * 50))
        monkeypatch.setattr(scanner_mod, 'BUSY_RETRY_SECONDS', 0)
        monkeypatch.setattr(scanner_mod.tempfile, 'tempdir', str(tmp_path))

        with pytest.raises(ScannerError):
            SaneAirscanScanner(DEVICE, timeout=60).scan_page(200)
        assert os.listdir(tmp_path) == []

    def test_other_errors_are_not_retried(self, monkeypatch, no_sleep):
        fake = FakeScanimage(failures=[b"sane_start: Document feeder out of documents"])
        monkeypatch.setattr(subprocess, 'run', fake)

        with pytest.raises(ScannerError, match="out of documents"):
            SaneAirscanScanner(DEVICE, timeout=60).scan_page(200)
        assert len(fake.commands) == 1


class TestProgressEstimate:
    def test_starts_from_the_measured_defaults(self):
        est = ScanTimeEstimator()
        assert est.expected(False) == DEFAULT_SECONDS[False] == 9.0
        assert est.expected(True) == DEFAULT_SECONDS[True] == 20.0

    def test_follows_recent_scans_of_the_same_kind(self):
        est = ScanTimeEstimator()
        est.record(False, 7.0)
        est.record(False, 9.0)
        assert est.expected(False) == 8.0
        assert est.expected(True) == 20.0    # colour untouched

    def test_only_the_last_few_count(self):
        est = ScanTimeEstimator()
        for seconds in (100, 100, 100, 100, 100, 10, 10, 10, 10, 10):
            est.record(False, seconds)
        assert est.expected(False) == 10.0

    def test_nonsense_durations_are_ignored(self):
        est = ScanTimeEstimator()
        est.record(False, 0)
        est.record(False, -3)
        assert est.expected(False) == 9.0

    def test_fraction_climbs_and_stops_short_of_done(self):
        assert progress_fraction(0, 9) == 0.0
        assert progress_fraction(4.5, 9) == pytest.approx(0.5)
        assert progress_fraction(30, 9) == PROGRESS_CAP   # a slow scan never shows 100% early

    def test_fraction_with_no_estimate_is_zero(self):
        assert progress_fraction(5, 0) == 0.0


class RecordingScanner:
    def __init__(self, path):
        self.path = path
        self.calls = []

    def is_available(self):
        return True

    def scan_page(self, dpi, colour=False):
        self.calls.append((dpi, colour))
        return self.path


class TestManagerColour:
    def test_greyscale_unless_asked(self, tmp_path):
        scanner = RecordingScanner(str(tmp_path / "p.jpg"))
        manager = ScannerManager(scanner=scanner, dpi=200)

        manager.scan_page()
        manager.colour = True
        manager.scan_page()

        assert scanner.calls == [(200, False), (200, True)]

    def test_rescan_keeps_the_current_mode(self, tmp_path):
        scanner = RecordingScanner(str(tmp_path / "p.jpg"))
        manager = ScannerManager(scanner=scanner, dpi=200)
        manager.colour = True
        manager.scan_page()

        manager.rescan_last()

        assert scanner.calls[-1] == (200, True)

    def test_records_how_long_a_scan_took(self, tmp_path, monkeypatch):
        import managers.scanner_manager as sm
        clock = iter([100.0, 107.0])
        monkeypatch.setattr(sm.time, 'monotonic', lambda: next(clock))
        manager = ScannerManager(scanner=RecordingScanner(str(tmp_path / "p.jpg")), dpi=200)

        manager.scan_page()

        assert manager.expected_scan_seconds() == 7.0

    def test_a_failed_scan_is_not_recorded(self, tmp_path):
        class Failing(RecordingScanner):
            def scan_page(self, dpi, colour=False):
                raise ScannerError("no")

        manager = ScannerManager(scanner=Failing(""), dpi=200)
        with pytest.raises(ScannerError):
            manager.scan_page()
        assert manager.expected_scan_seconds() == 9.0

    def test_sim_scanner_accepts_the_colour_flag(self, tmp_path):
        path = SimScanner(str(tmp_path / "sim"), page_count=1).scan_page(100, colour=True)
        assert os.path.exists(path)
        os.remove(path)


class TestScannerModeSetting:
    def test_default_is_grey(self, monkeypatch):
        from config import get_config
        monkeypatch.delenv('SCANNER_MODE', raising=False)
        assert get_config().scanner_colour_default is False

    @pytest.mark.parametrize("value,expected", [("Color", True), ("colour", True), ("Gray", False), ("", False)])
    def test_env_values(self, monkeypatch, value, expected):
        from config import get_config
        monkeypatch.setenv('SCANNER_MODE', value)
        assert get_config().scanner_colour_default is expected


class TestScannerScreen:
    @pytest.fixture
    def view(self):
        from screens.scanner.view import ScannerScreenView
        return ScannerScreenView()

    def test_colour_button_states_its_cost(self, view):
        assert "faster" in view.colour_button.text()
        view.colour_button.click()
        assert "slower" in view.colour_button.text()

    def test_toggling_announces_the_new_mode(self, view):
        seen = []
        view.colour_toggled.connect(seen.append)
        view.colour_button.click()
        view.colour_button.click()
        assert seen == [True, False]

    def test_set_colour_syncs_without_announcing(self, view):
        seen = []
        view.colour_toggled.connect(seen.append)
        view.set_colour(True)
        assert view.colour_button.isChecked() and "slower" in view.colour_button.text()
        assert seen == []

    def test_colour_cannot_change_mid_scan(self, view):
        view.set_busy(True)
        assert not view.colour_button.isEnabled()
        view.set_busy(False)
        assert view.colour_button.isEnabled()

    def test_progress_bar_shows_and_hides(self, view):
        assert view.progress_bar.isHidden()
        view.show_progress(0.5)
        assert not view.progress_bar.isHidden() and view.progress_bar.value() == 50
        view.hide_progress()
        assert view.progress_bar.isHidden() and view.progress_bar.value() == 0

    def test_reset_hides_progress_and_applies_the_default_mode(self, view):
        view.show_progress(0.7)
        view.reset(colour=True)
        assert view.progress_bar.isHidden()
        assert view.colour_button.isChecked()


class TestScannerControllerProgress:
    @pytest.fixture
    def controller(self, tmp_path, monkeypatch):
        monkeypatch.setenv('SIM_SCANNER_DIR', str(tmp_path / "sim"))
        from screens.scanner.controller import ScannerController
        main_app = SimpleNamespace(stacked_widget=SimpleNamespace(currentWidget=lambda: None),
                                   start_global_countdown=lambda s: None)
        return ScannerController(main_app)

    def test_scan_starts_the_bar_and_the_end_of_the_scan_hides_it(self, controller):
        controller.model.manager.timings.record(False, 6.0)

        controller._start_progress("Scanning")
        assert controller.progress_timer.isActive()
        assert not controller.view.progress_bar.isHidden()
        assert "about 6 seconds" in controller.view.status_banner.findChild(QLabel).text()

        controller._on_busy_changed(False)
        assert not controller.progress_timer.isActive()
        assert controller.view.progress_bar.isHidden()

    def test_entering_the_screen_starts_in_the_configured_mode(self, controller, monkeypatch):
        monkeypatch.setenv('SCANNER_MODE', 'Color')
        controller.on_enter()
        assert controller.model.colour is True
        assert controller.view.colour_button.isChecked()
        controller.on_leave()

    def test_the_toggle_reaches_the_scanner_manager(self, controller):
        controller.on_enter()
        controller.view.colour_button.click()
        assert controller.model.manager.colour is True
        controller.on_leave()
