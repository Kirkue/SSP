# managers/scanner.py
#
# Hardware abstraction for the flatbed document scanner (project_objectives.txt
# #8 — Scanner Module). SaneAirscanScanner shells out to `scanimage` (SANE's
# CLI, backed by the sane-airscan/eSCL driverless backend) the same way
# printer_manager.py shells out to `lp`/`lpstat` for CUPS — no python-sane
# binding is used. SimScanner stands in for laptop development (SIM_MODE),
# returning canned page images instead of talking to real hardware, the same
# role usb_file_manager.py's SIM_USB_DIR plays for USB drives.

import os
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod

# After a scan the scanner stays "Device busy" for ~2.6 s (measured on the kiosk), so a
# scan started straight after another (the next page) retries for up to this long.
BUSY_RETRY_SECONDS = 10
BUSY_RETRY_INTERVAL = 1


class ScannerError(Exception):
    """Raised for any scanner failure — missing hardware, timeout, bad output."""


class ScannerInterface(ABC):
    @abstractmethod
    def scan_page(self, dpi: int, colour: bool = False) -> str:
        """Scan one page and return the path to a fresh single-page image (a JPEG on the
        real scanner). Greyscale unless `colour`, which takes about twice as long."""

    @abstractmethod
    def is_available(self) -> bool:
        """Whether the scanner can be reached right now."""


class SaneAirscanScanner(ScannerInterface):
    """Talks to the kiosk's HP Smart Tank over eSCL (driverless) via the
    `scanimage` CLI. Flatbed only — no ADF flags, one page per call,
    matching project_objectives.txt #8. The device string comes from .env;
    on the kiosk it's `escl:http://localhost:60000` (the ipp-usb port, the
    same for any model), and `scanimage -L` lists the alternatives. eSCL
    device indices aren't stable across reboots, so it's never
    auto-discovered here."""

    def __init__(self, device: str, timeout: int):
        self.device = device
        self.timeout = timeout

    def is_available(self) -> bool:
        if not self.device:
            return False
        try:
            result = subprocess.run(
                ["scanimage", "-L"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0 and self.device in result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def scan_page(self, dpi: int, colour: bool = False) -> str:
        if not self.device:
            raise ScannerError(
                "No scanner device configured — set SCANNER_DEVICE in .env "
                "(run `scanimage -L` on the kiosk to find it)."
            )

        # Gray + JPEG measured ~9 s a page against ~20 s for Color + PNG (docs/remaining-work.md 2.3).
        fd, output_path = tempfile.mkstemp(suffix=".jpg", prefix="scan-page-")
        os.close(fd)

        command = [
            "scanimage",
            "-d", self.device,
            "--format=jpeg",
            f"--mode={'Color' if colour else 'Gray'}",
            "--resolution", str(dpi),
        ]
        busy_deadline = time.monotonic() + BUSY_RETRY_SECONDS
        while True:
            try:
                with open(output_path, "wb") as out_file:
                    subprocess.run(
                        command, stdout=out_file, stderr=subprocess.PIPE,
                        timeout=self.timeout, check=True,
                    )
                break
            except FileNotFoundError:
                self._cleanup(output_path)
                raise ScannerError("'scanimage' is not installed — is sane-airscan set up on this kiosk?")
            except subprocess.TimeoutExpired:
                self._cleanup(output_path)
                raise ScannerError(f"Scan timed out after {self.timeout}s — check the scanner connection.")
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b"").decode(errors="replace").strip()
                if "busy" in stderr.lower():
                    if time.monotonic() < busy_deadline:
                        time.sleep(BUSY_RETRY_INTERVAL)
                        continue
                    self._cleanup(output_path)
                    raise ScannerError("The scanner is busy. Please wait a moment and try again.")
                self._cleanup(output_path)
                raise ScannerError(f"scanimage failed: {stderr or 'unknown error'}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            self._cleanup(output_path)
            raise ScannerError("Scan produced no image data.")

        return output_path

    @staticmethod
    def _cleanup(path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


class SimScanner(ScannerInterface):
    """SIM_MODE stand-in: cycles through a small set of canned page images
    seeded into `sim_dir` on first use, so multi-page/rescan/cancel logic
    can be exercised without hardware. Each call copies the next canned
    file to a *fresh* temp path — never the seed file itself — so callers
    can freely delete per-page files without disturbing the seed set."""

    def __init__(self, sim_dir: str, page_count: int = 3):
        self.sim_dir = sim_dir
        self.page_count = page_count
        self._next_index = 0
        self._seed()

    def is_available(self) -> bool:
        return True

    def _seed(self):
        os.makedirs(self.sim_dir, exist_ok=True)
        existing = [f for f in os.listdir(self.sim_dir) if f.lower().endswith('.png')]
        if len(existing) >= self.page_count:
            return

        import fitz  # PyMuPDF

        for i in range(self.page_count):
            path = os.path.join(self.sim_dir, f"sim_page_{i + 1}.png")
            if os.path.exists(path):
                continue
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), f"SIM_MODE scanned page {i + 1}")
            pix = page.get_pixmap(dpi=100)
            pix.save(path)
            doc.close()
        print(f"📄 Seeded {self.page_count} sample page(s) into SIM_SCANNER_DIR: {self.sim_dir}")

    def scan_page(self, dpi: int, colour: bool = False) -> str:
        canned = sorted(f for f in os.listdir(self.sim_dir) if f.lower().endswith('.png'))
        if not canned:
            raise ScannerError(f"No canned pages found in {self.sim_dir}")

        source = os.path.join(self.sim_dir, canned[self._next_index % len(canned)])
        self._next_index += 1

        fd, dest = tempfile.mkstemp(suffix=".png", prefix="sim-scan-page-")
        os.close(fd)
        shutil.copyfile(source, dest)
        return dest


def build_scanner_from_config(config=None) -> ScannerInterface:
    """SIM_MODE -> SimScanner, else SaneAirscanScanner, matching the
    SIM_MODE convention already used by sms_manager.py / printer_thread.py."""
    if config is None:
        from config import get_config
        config = get_config()

    if config.sim_mode:
        return SimScanner(config.sim_scanner_dir, config.sim_scanner_page_count)
    return SaneAirscanScanner(config.scanner_device, config.scanner_timeout)
