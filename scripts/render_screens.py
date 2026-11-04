"""Render every kiosk screen to a PNG exactly as the 1920x1080 kiosk panel shows it.

The reference picture for UI work: the font ships with the app and the Qt
environment is pinned (ui/theme.py, ui/scaling.py), so these match the kiosk
whether they're rendered on a laptop or on the Pi. Nothing touches the real
hardware or database: pigpio is blocked, SIM_MODE is on and the screens read a
throwaway SQLite file.

    make screenshots                 # -> screenshots/<screen>.png
    python scripts/render_screens.py --out DIR --height 1080 homepage payment
"""

import argparse
import os
import sys
import tempfile

SSP_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'SSP'))

# Screen name -> controller class in screens.<name>. Customer screens first.
SCREENS = {
    "idle": "IdleController",
    "homepage": "HomepageController",
    "usb": "USBController",
    "wifi": "WifiController",
    "email": "EmailController",
    "scanner": "ScannerController",
    "scan_destination": "ScanDestinationController",
    "scan_result": "ScanResultController",
    "file_browser": "FileBrowserController",
    "print_options": "PrintOptionsController",
    "payment": "PaymentController",
    "voucher": "VoucherController",
    "thank_you": "ThankYouController",
    "admin": "AdminController",
}


# Not screens: a popup over a screen, rendered on top of the homepage it opens from.
POPUPS = ("voucher_balance_popup",)


def prepare_environment():
    """Headless Qt, simulated hardware and a temp database. Call before importing
    anything from SSP/."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["SIM_MODE"] = "true"
    # The kiosk has a QR reader, so its hint shows whatever this machine's .env says.
    # Never opened: the reader is started by main_app, which isn't run here.
    os.environ["QR_READER_PORT"] = "/dev/render-screens-reader"
    sys.modules["pigpio"] = None  # `import pigpio` fails, so GPIO code runs simulated
    if SSP_DIR not in sys.path:
        sys.path.insert(0, SSP_DIR)

    import database.db_manager as db_manager
    from database.models import init_db

    temp_db = os.path.join(tempfile.mkdtemp(prefix="ssp-screens-"), "screens.db")
    init_db(temp_db)
    real_init = db_manager.DatabaseManager.__init__

    def init_on_temp_db(self, db_name="ssp_database.db", db_path=None):
        real_init(self, db_name, db_path or temp_db)

    db_manager.DatabaseManager.__init__ = init_on_temp_db


def fill_live_content(name, screen):
    """Show what on_enter() and a failed code would add, so the screen is checked
    at its tallest: an empty address and QR hid the bottom being cut off."""
    if name == "wifi":
        screen.view.set_portal_hint("https://10.3.141.1:8000/upload")
    elif name == "email":
        screen.view.set_email_hint("aiospark.uploads@gmail.com", "PRINT")
    if name in ("wifi", "email"):
        screen.view.show_status("Invalid or expired code. Please try again.")
    if name == "scanner":
        screen.view.update_page_count(2)
        screen.view.show_preview(sample_page_image(), 2)
        screen.view.show_status("Scan timed out after 60s — check the scanner connection.")
    if name == "thank_you":
        screen.model.show_no_paper_error(0)  # its longest message: the admin's refill hint


def sample_page_image():
    """A scanned-page stand-in: the first page of a test PDF as a PNG."""
    import fitz

    path = os.path.join(tempfile.mkdtemp(prefix="ssp-screens-"), "page.png")
    with fitz.open(os.path.join(SSP_DIR, "..", "test_pdfs", "Rootlocus-Plotting-1.pdf")) as doc:
        doc[0].get_pixmap(dpi=100).save(path)
    return path


def build_popup_preview(name):
    """The balance popup open over the homepage, showing a found Voucher: its tallest state
    (keypad, result and the saved note), so a popup too tall for the panel is caught."""
    import importlib
    from datetime import datetime
    from unittest.mock import MagicMock

    from PyQt5.QtCore import QSize
    from PyQt5.QtWidgets import QVBoxLayout, QWidget

    class Host(QWidget):
        def __init__(self):
            super().__init__()
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.background = importlib.import_module("screens.homepage").HomepageController(MagicMock())
            layout.addWidget(self.background)
            self.popup = importlib.import_module("screens.voucher_balance").VoucherBalanceController(
                MagicMock(), parent_widget=self)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self.popup.is_open:
                self.popup.view.setGeometry(self.rect())

        def minimumSizeHint(self):
            card = self.popup.view.card.sizeHint()
            return QSize(card.width(), max(self.background.minimumSizeHint().height(), card.height() + 80))

    host = Host()
    popup = host.popup
    popup.open()
    model = popup.model
    model.state, model.remaining, model.expires_at = model.FOUND, 50, datetime(2027, 1, 31)
    popup.view.render(model, "Saved for this session: you can use it when you pay.")
    return host


def build_screen(name):
    """The real controller for `name`, wired to a stand-in main app."""
    import importlib
    from unittest.mock import MagicMock

    if name in POPUPS:
        return build_popup_preview(name)

    module = importlib.import_module(f"screens.{name}")
    screen = getattr(module, SCREENS[name])(MagicMock())
    fill_live_content(name, screen)
    return screen


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("screens", nargs="*", metavar="screen",
                        help=f"default: all of {', '.join(list(SCREENS) + list(POPUPS))}")
    parser.add_argument("--out", default="screenshots")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    unknown = set(args.screens) - set(SCREENS) - set(POPUPS)
    if unknown:
        parser.error(f"unknown screen(s): {', '.join(sorted(unknown))}")

    prepare_environment()
    from ui.scaling import pin_render_environment, ui_scale_factor
    pin_render_environment()
    scale = ui_scale_factor(args.height, os.environ.get("UI_SCALE", ""))
    os.environ["QT_SCALE_FACTOR"] = str(scale)

    from PyQt5.QtWidgets import QApplication
    from ui.theme import apply_theme
    app = QApplication(sys.argv)
    apply_theme(app)

    os.makedirs(args.out, exist_ok=True)
    width, height = round(args.width / scale), round(args.height / scale)
    print(f"Rendering at {args.width}x{args.height} (scale {scale}, {width}x{height} logical) into {args.out}/")
    overflowed = []
    for name in args.screens or [*SCREENS, *POPUPS]:
        screen = build_screen(name)
        screen.resize(width, height)
        screen.show()
        app.processEvents()
        needed = screen.minimumSizeHint().height()
        screen.grab().save(os.path.join(args.out, f"{name}.png"))
        screen.hide()
        overflow = f"  OVERFLOWS by {needed - height}px" if needed > height else ""
        print(f"  {name:<18} needs {needed}px of {height}px{overflow}")
        if overflow:
            overflowed.append(name)
    if overflowed:
        sys.exit(f"Too tall for the panel: {', '.join(overflowed)}")


if __name__ == "__main__":
    main()
