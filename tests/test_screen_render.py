"""
Every screen renders with the bundled font and fits the 1080-tall kiosk panel.
Runs scripts/render_screens.py (the `make screenshots` renderer) in its own
process, since it blocks pigpio and points DatabaseManager at a temp file.
"""
import os
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtGui import QFontInfo  # noqa: E402
from PyQt5.QtWidgets import QApplication, QLabel  # noqa: E402

from ui.theme import FONT, apply_theme  # noqa: E402

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))


def test_text_uses_the_bundled_font_in_pixels():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    info = QFontInfo(QLabel("x").font())
    assert info.family() == "Inter"
    assert info.pixelSize() == FONT["size_md"]


def test_every_screen_fits_the_kiosk_panel(tmp_path):
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "scripts/render_screens.py", "--out", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "OVERFLOWS" not in result.stdout
    assert len(list(tmp_path.glob("*.png"))) == 15
