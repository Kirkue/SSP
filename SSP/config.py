"""
Configuration Module for SSP (Self-Service Printer) Application

Loads application configuration from a .env file and provides type-safe access
to configuration values. Application will exit if .env file is not found.

Configuration Categories:
- Page Pricing: Prices for black & white and color printing
- Printer Settings: Printer name, timeout, and retry attempts
- System Settings: Color mode, copy limits
- Analysis Settings: PDF analysis DPI, color tolerance, thresholds
"""

import os
import sys
from typing import TypeVar, cast

ValueType = TypeVar("ValueType", str, int, float, bool)

# GPIO pins per kiosk model (KIOSK_MODEL in .env). 'old' is the kiosk tested so far,
# found by watching every GPIO while coins went in and each hopper ran (2026-10-15).
# 'new' was checked the same way on that kiosk (2026-10-22); its coin pin and hopper
# sensor pins differ from 'old' (hopper A/B sensors swapped).
KIOSK_MODEL_PINS = {
    'old': {
        'COIN_PIN': 12, 'BILL_PIN': 18, 'COIN_INHIBIT_PIN': 22, 'BILL_INHIBIT_PIN': 23,
        'HOPPER_A_SIGNAL_PIN': 9, 'HOPPER_A_ENABLE_PIN': 24,
        'HOPPER_B_SIGNAL_PIN': 26, 'HOPPER_B_ENABLE_PIN': 25,
    },
    'new': {
        'COIN_PIN': 17, 'BILL_PIN': 18, 'COIN_INHIBIT_PIN': 22, 'BILL_INHIBIT_PIN': 23,
        'HOPPER_A_SIGNAL_PIN': 26, 'HOPPER_A_ENABLE_PIN': 24,
        'HOPPER_B_SIGNAL_PIN': 9, 'HOPPER_B_ENABLE_PIN': 25,
    },
}


class Config:
    """
    Configuration class that loads and provides access to settings from .env file.

    All configuration values are loaded from environment variables and are
    accessible via properties with automatic type conversion.
    """

    def __init__(self, env_file: str = ".env"):
        """
        Initialize configuration from .env file.

        Args:
            env_file: Path to .env configuration file (default: ".env")

        Raises:
            SystemExit: If .env file is not found
        """
        self.env_file = env_file
        self._check_env_file_exists()
        self._load_env_file()

    def _check_env_file_exists(self):
        """
        Verify that .env file exists.

        Exits application with error message if file is not found.
        """
        if not os.path.exists(self.env_file):
            print(f"❌ Configuration file '{self.env_file}' not found!")
            print("Please create a .env file with your configuration settings.")
            sys.exit(1)

    def _load_env_file(self):
        """
        Load environment variables from .env file.

        Parses key=value pairs and sets them as environment variables.
        Supports comments (lines starting with #) and quoted values.
        """
        with open(self.env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Strip inline comments (e.g. KEY=value  # comment)
                    if '#' in value:
                        value = value.split('#')[0].strip()

                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    # Shell env takes precedence over .env (allows SIM_MODE=true make run-sim)
                    os.environ.setdefault(key, value)

    def get(self, key: str, value_type: type[ValueType] = str) -> ValueType:
        """
        Get configuration value with type conversion.

        Args:
            key: Configuration key
            value_type: Type to convert the value to (str, int, float, bool)

        Returns:
            Configuration value converted to specified type

        Raises:
            KeyError: If the configuration key is not found
            ValueError: If the value cannot be converted to the specified type
        """
        if key not in os.environ:
            raise KeyError(f"Configuration key '{key}' not found in .env file")

        value = os.environ[key]

        try:
            if value_type is bool:
                return cast(ValueType, value.lower() in ('true', '1', 'yes', 'on'))
            elif value_type is int:
                return cast(ValueType, int(value))
            elif value_type is float:
                return cast(ValueType, float(value))
            else:
                return cast(ValueType, str(value))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Could not convert '{key}={value}' to {value_type.__name__}: {e}")

    # Page pricing configuration

    @property
    def black_and_white_price(self) -> float:
        """Get price per page for black and white printing."""
        return self.get('BLACK_AND_WHITE_PRICE', float)

    @property
    def color_price(self) -> float:
        """Get price per page for color printing."""
        return self.get('COLOR_PRICE', float)

    # Printer configuration

    @property
    def printer_name(self) -> str:
        """Get CUPS printer name."""
        return self.get('PRINTER_NAME', str)

    @property
    def printer_timeout(self) -> int:
        """Get printer command timeout in seconds."""
        return self.get('PRINTER_TIMEOUT', int)

    @property
    def printer_retry_attempts(self) -> int:
        """Get number of printer retry attempts."""
        return self.get('PRINTER_RETRY_ATTEMPTS', int)

    # System settings

    @property
    def default_color_mode(self) -> str:
        """Get default color mode ('Color' or 'Black and White')."""
        return self.get('DEFAULT_COLOR_MODE', str)

    @property
    def max_copies(self) -> int:
        """Get maximum number of copies allowed per print job."""
        return self.get('MAX_COPIES', int)

    @property
    def min_copies(self) -> int:
        """Get minimum number of copies required per print job."""
        return self.get('MIN_COPIES', int)

    # Analysis settings

    @property
    def pdf_analysis_dpi(self) -> int:
        """Get DPI used for PDF analysis (higher = more accurate but slower)."""
        return self.get('PDF_ANALYSIS_DPI', int)

    @property
    def color_tolerance(self) -> int:
        """Get color tolerance for distinguishing color vs grayscale (0-255)."""
        return self.get('COLOR_TOLERANCE', int)

    @property
    def pixel_count_threshold(self) -> int:
        """Get minimum pixel count threshold for color detection."""
        return self.get('PIXEL_COUNT_THRESHOLD', int)

    # Inactivity timeout (managers/timeout_manager.py)

    @property
    def timeout_warning_seconds(self) -> int:
        """Seconds left at which the "Still there?" prompt appears (default 15)."""
        try:
            return max(1, self.get('TIMEOUT_WARNING_SECONDS', int))
        except KeyError:
            return 15

    @property
    def timeout_extend_seconds(self) -> int:
        """Seconds the prompt's button adds (default 30)."""
        try:
            return max(1, self.get('TIMEOUT_EXTEND_SECONDS', int))
        except KeyError:
            return 30

    # Supplies

    @property
    def low_paper_alert_sheets(self) -> int:
        """Sheets left at or below which the operator gets a low-paper SMS (default 10).
        The one place this threshold lives; the kiosk still stops taking customers at 3."""
        try:
            return max(0, self.get('LOW_PAPER_ALERT_SHEETS', int))
        except KeyError:
            return 10

    @property
    def ink_low_alert_percent(self) -> float:
        """Estimated tank level (%) at or below which the operator gets a low-ink SMS (default 20).
        Low ink never stops the kiosk by itself; only an admin marking a tank empty does."""
        try:
            return self.get('INK_LOW_ALERT_PERCENT', float)
        except KeyError:
            return 20.0

    # Bottle yields (pages at the standard 5% coverage) the ink estimate is scaled by. Defaults are
    # HP's data sheet figures for the Smart Tank 670 (GT53XL black ~6,200 pages, GT52 colour
    # ~9,100 pages per bottle, ISO/IEC 24712 pages). A too-high yield makes the estimate drain
    # too slowly (docs/remaining-work.md 2.5).

    @property
    def ink_yield_black_pages(self) -> int:
        """Pages one black bottle prints at standard coverage."""
        try:
            return max(1, self.get('INK_YIELD_BLACK_PAGES', int))
        except KeyError:
            return 6200

    @property
    def ink_yield_color_pages(self) -> int:
        """Pages one colour bottle prints at standard coverage."""
        try:
            return max(1, self.get('INK_YIELD_COLOR_PAGES', int))
        except KeyError:
            return 9100

    # SMS / hardware settings

    @property
    def phone_number(self) -> str:
        """Get admin phone number for SMS alerts."""
        return self.get('PHONE_NUMBER', str)

    # Acceptor and hopper pins. KIOSK_MODEL picks a pin set from KIOSK_MODEL_PINS;
    # a pin set in .env (e.g. COIN_PIN) overrides the model's value.

    @property
    def kiosk_model(self) -> str:
        """Kiosk model whose wiring to use: 'old' (default) or 'new'."""
        try:
            model = self.get('KIOSK_MODEL', str).strip().lower() or 'old'
        except KeyError:
            return 'old'
        if model not in KIOSK_MODEL_PINS:
            raise ValueError(f"Unknown KIOSK_MODEL '{model}' "
                             f"(expected one of: {', '.join(KIOSK_MODEL_PINS)})")
        return model

    def _pin(self, key: str) -> int:
        """GPIO pin from .env if set, else from the kiosk model's pin set."""
        try:
            return self.get(key, int)
        except KeyError:
            return KIOSK_MODEL_PINS[self.kiosk_model][key]

    @property
    def coin_pin(self) -> int:
        """Get GPIO pin number for coin acceptor pulse input."""
        return self._pin('COIN_PIN')

    @property
    def bill_pin(self) -> int:
        """Get GPIO pin number for bill acceptor pulse input."""
        return self._pin('BILL_PIN')

    @property
    def coin_inhibit_pin(self) -> int:
        """Get GPIO pin number for coin acceptor inhibit/enable (active high)."""
        return self._pin('COIN_INHIBIT_PIN')

    @property
    def bill_inhibit_pin(self) -> int:
        """Get GPIO pin number for bill acceptor inhibit/enable (active low)."""
        return self._pin('BILL_INHIBIT_PIN')

    # Coin pulse noise filtering (managers/persistent_gpio.py). The coin line picks
    # up sub-millisecond spikes; real pulses are ~15 ms (Fast) to ~100 ms (Slow).

    @property
    def coin_pulse_filter(self) -> bool:
        """Filter coin pulses by width. False = legacy falling-edge counting (diagnostics)."""
        try:
            return self.get('COIN_PULSE_FILTER', bool)
        except KeyError:
            return True

    @property
    def coin_glitch_filter_us(self) -> int:
        """pigpio glitch filter on the coin pin: ignore level changes shorter than this (µs)."""
        try:
            return self.get('COIN_GLITCH_FILTER_US', int)
        except KeyError:
            return 5000

    @property
    def coin_pulse_min_ms(self) -> float:
        """Shortest low pulse on the coin pin counted as a coin pulse (ms)."""
        try:
            return self.get('COIN_PULSE_MIN_MS', float)
        except KeyError:
            return 10.0

    @property
    def coin_pulse_max_ms(self) -> float:
        """Longest low pulse on the coin pin counted as a coin pulse (ms)."""
        try:
            return self.get('COIN_PULSE_MAX_MS', float)
        except KeyError:
            return 150.0

    # Bill pulse noise filtering, as for coins. The bill line picks up sub-0.1 ms
    # spikes (in and between bills); real pulses are ~50 ms (new kiosk, 2026-10-22).

    @property
    def bill_pulse_filter(self) -> bool:
        """Filter bill pulses by width. False = legacy falling-edge counting (diagnostics)."""
        try:
            return self.get('BILL_PULSE_FILTER', bool)
        except KeyError:
            return True

    @property
    def bill_glitch_filter_us(self) -> int:
        """pigpio glitch filter on the bill pin: ignore level changes shorter than this (µs)."""
        try:
            return self.get('BILL_GLITCH_FILTER_US', int)
        except KeyError:
            return 5000

    @property
    def bill_pulse_min_ms(self) -> float:
        """Shortest low pulse on the bill pin counted as a bill pulse (ms)."""
        try:
            return self.get('BILL_PULSE_MIN_MS', float)
        except KeyError:
            return 20.0

    @property
    def bill_pulse_max_ms(self) -> float:
        """Longest low pulse on the bill pin counted as a bill pulse (ms)."""
        try:
            return self.get('BILL_PULSE_MAX_MS', float)
        except KeyError:
            return 150.0

    # Coin hoppers (managers/hopper_manager.py), pins from the kiosk model as above.

    @property
    def hopper_a_signal_pin(self) -> int:
        """Get GPIO pin number for hopper A's (₱1) coin-out sensor."""
        return self._pin('HOPPER_A_SIGNAL_PIN')

    @property
    def hopper_a_enable_pin(self) -> int:
        """Get GPIO pin number for hopper A's (₱1) motor enable (active low)."""
        return self._pin('HOPPER_A_ENABLE_PIN')

    @property
    def hopper_b_signal_pin(self) -> int:
        """Get GPIO pin number for hopper B's (₱5) coin-out sensor."""
        return self._pin('HOPPER_B_SIGNAL_PIN')

    @property
    def hopper_b_enable_pin(self) -> int:
        """Get GPIO pin number for hopper B's (₱5) motor enable (active low)."""
        return self._pin('HOPPER_B_ENABLE_PIN')

    # Admin access

    @property
    def admin_pin(self) -> str:
        """PIN required to open the admin dialog (screens/dialogs/pin_dialog/)."""
        try:
            return self.get('ADMIN_PIN', str)
        except KeyError:
            return "1234"

    # Display settings

    @property
    def force_fullscreen(self) -> bool:
        """Force fullscreen mode regardless of screen size."""
        return self.get('FORCE_FULLSCREEN', bool)

    @property
    def window_width(self) -> int:
        """Get preferred window width for windowed mode."""
        return self.get('WINDOW_WIDTH', int)

    @property
    def window_height(self) -> int:
        """Get preferred window height for windowed mode."""
        return self.get('WINDOW_HEIGHT', int)

    @property
    def fullscreen_threshold_width(self) -> int:
        """Get screen width threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_WIDTH', int)

    @property
    def fullscreen_threshold_height(self) -> int:
        """Get screen height threshold below which fullscreen is used."""
        return self.get('FULLSCREEN_THRESHOLD_HEIGHT', int)

    @property
    def sim_mode(self) -> bool:
        """Skip GPIO, CUPS, and modem — set SIM_MODE=true for laptop development."""
        try:
            return self.get('SIM_MODE', bool)
        except KeyError:
            return False

    @property
    def qr_reader_port(self) -> str:
        """Serial port of the kiosk QR reader (e.g. /dev/ttyACM0, /dev/cu.usbmodem*).
        Blank or unset means no reader: the kiosk runs with typed codes only."""
        try:
            return self.get('QR_READER_PORT', str).strip()
        except KeyError:
            return ""

    @property
    def ui_scale(self) -> str:
        """UI_SCALE: a number scales the whole touchscreen UI by that much; blank or
        "auto" picks a scale from the screen height (ui/scaling.py)."""
        try:
            return self.get('UI_SCALE', str).strip()
        except KeyError:
            return ""

    # Web backend (FastAPI) settings

    @property
    def docs_enabled(self) -> bool:
        """Serve /docs and /redoc — must be false in production (see project_objectives.txt)."""
        try:
            return self.get('API_DOCS_ENABLED', bool)
        except KeyError:
            return False

    # Wi-Fi upload portal (webapp/routers/upload.py)

    @property
    def wifi_upload_dir(self) -> str:
        """Directory uploaded PDFs are saved to before being handed to SessionManager."""
        try:
            return self.get('WIFI_UPLOAD_DIR', str)
        except KeyError:
            return "SSP/database/wifi_uploads"

    @property
    def max_upload_size_mb(self) -> int:
        """Reject Wi-Fi uploads larger than this (megabytes)."""
        try:
            return self.get('MAX_UPLOAD_SIZE_MB', int)
        except KeyError:
            return 25

    @property
    def wifi_portal_port(self) -> int:
        """Port the Wi-Fi portal's Uvicorn instance listens on. The hotspot
        firewall (scripts/setup_hotspot.py) opens exactly this port on the
        hotspot interface, so both read it from here."""
        try:
            return self.get('WIFI_PORTAL_PORT', int)
        except KeyError:
            return 8000

    @property
    def wifi_captive_port(self) -> int:
        """Plain-HTTP port the captive-portal probe responder (webapp/captive.py)
        listens on. The hotspot firewall redirects the hotspot's port 80 here."""
        try:
            return self.get('WIFI_CAPTIVE_PORT', int)
        except KeyError:
            return 8080

    @property
    def wifi_tls_certfile(self) -> str:
        """
        Path to the TLS cert for the Wi-Fi portal's Uvicorn instance
        (project_objectives.txt module 5). Generated by
        scripts/generate_tls_cert.py. WebAppThreadManager.from_config() only
        enables HTTPS when this and wifi_tls_keyfile both point at existing
        files — otherwise it serves plain HTTP.
        """
        try:
            return self.get('WIFI_TLS_CERTFILE', str)
        except KeyError:
            return "certs/cert.pem"

    @property
    def wifi_tls_keyfile(self) -> str:
        """Path to the TLS private key paired with wifi_tls_certfile."""
        try:
            return self.get('WIFI_TLS_KEYFILE', str)
        except KeyError:
            return "certs/key.pem"

    # Kiosk hotspot (scripts/setup_hotspot.py) — see
    # docs/adr/0007-own-hotspot-replaces-raspap-captive-portal.md. Read at
    # install time by the setup script; the app doesn't act on them yet.

    @property
    def kiosk_id(self) -> str:
        """This kiosk's ID, the last part of print.<domain>/k/<KIOSK_ID>."""
        try:
            return self.get('KIOSK_ID', str).strip()
        except KeyError:
            return ""

    @property
    def wifi_hotspot_enabled(self) -> bool:
        """Whether the setup script enables the hostapd/dnsmasq hotspot."""
        try:
            return self.get('WIFI_HOTSPOT_ENABLED', bool)
        except KeyError:
            return False

    @property
    def wifi_hotspot_interface(self) -> str:
        """Wi-Fi interface the hotspot broadcasts on."""
        try:
            return self.get('WIFI_HOTSPOT_INTERFACE', str).strip()
        except KeyError:
            return "wlan0"

    @property
    def wifi_hotspot_ssid(self) -> str:
        """Network name phones see (an open network, no password)."""
        try:
            return self.get('WIFI_HOTSPOT_SSID', str)
        except KeyError:
            return "AIO-SPARK"

    @property
    def wifi_hotspot_country(self) -> str:
        """Two-letter Wi-Fi regulatory country code (hostapd country_code)."""
        try:
            return self.get('WIFI_HOTSPOT_COUNTRY', str).strip().upper()
        except KeyError:
            return "PH"

    @property
    def wifi_hotspot_channel(self) -> int:
        """2.4 GHz channel the hotspot broadcasts on."""
        try:
            return self.get('WIFI_HOTSPOT_CHANNEL', int)
        except KeyError:
            return 6

    @property
    def wifi_hotspot_address(self) -> str:
        """The Pi's own address on the hotspot, with prefix (e.g. 10.3.141.1/24).
        Must be the first host of its subnet; the rest is handed out by DHCP."""
        try:
            return self.get('WIFI_HOTSPOT_ADDRESS', str).strip()
        except KeyError:
            return "10.3.141.1/24"

    @property
    def portal_hostname(self) -> str:
        """The Portal's permanent name, print.<domain>. dnsmasq answers it
        with the hotspot address."""
        try:
            return self.get('PORTAL_HOSTNAME', str).strip().lower()
        except KeyError:
            return "print.aio-spark.example"

    # Email intake (managers/adapters/email_adapter.py) — defaults below match
    # the greenmail dev server in managers/adapters/greenmail/docker-compose.yml.
    # Override all of these in .env before pointing at the real dedicated
    # Gmail account (Gmail needs EMAIL_USE_SSL=true, IMAP port 993, an app
    # password, etc.) — no code changes required for that swap.

    @property
    def email_imap_host(self) -> str:
        try:
            return self.get('EMAIL_IMAP_HOST', str)
        except KeyError:
            return "127.0.0.1"

    @property
    def email_imap_port(self) -> int:
        try:
            return self.get('EMAIL_IMAP_PORT', int)
        except KeyError:
            return 3143

    @property
    def email_smtp_host(self) -> str:
        try:
            return self.get('EMAIL_SMTP_HOST', str)
        except KeyError:
            return "127.0.0.1"

    @property
    def email_smtp_port(self) -> int:
        try:
            return self.get('EMAIL_SMTP_PORT', int)
        except KeyError:
            return 3025

    @property
    def email_use_ssl(self) -> bool:
        try:
            return self.get('EMAIL_USE_SSL', bool)
        except KeyError:
            return False

    @property
    def email_user(self) -> str:
        try:
            return self.get('EMAIL_USER', str)
        except KeyError:
            return "test@example.com"

    @property
    def email_password(self) -> str:
        try:
            return self.get('EMAIL_PASSWORD', str)
        except KeyError:
            return "test"

    @property
    def email_mailbox(self) -> str:
        try:
            return self.get('EMAIL_MAILBOX', str)
        except KeyError:
            return "INBOX"

    @property
    def email_subject_keyword(self) -> str:
        """Required in the subject line for an email to be treated as a print request."""
        try:
            return self.get('EMAIL_SUBJECT_KEYWORD', str)
        except KeyError:
            return "DEMO_TRIGGER"

    @property
    def email_poll_interval_seconds(self) -> int:
        try:
            return self.get('EMAIL_POLL_INTERVAL_SECONDS', int)
        except KeyError:
            return 10

    @property
    def email_upload_dir(self) -> str:
        try:
            return self.get('EMAIL_UPLOAD_DIR', str)
        except KeyError:
            return "SSP/database/email_uploads"

    @property
    def email_max_attachment_size_mb(self) -> int:
        try:
            return self.get('EMAIL_MAX_ATTACHMENT_SIZE_MB', int)
        except KeyError:
            return 25

    # Scanner module (managers/scanner.py, managers/scanner_manager.py)

    @property
    def scanner_device(self) -> str:
        """sane-airscan device string for the flatbed scanner (run
        `scanimage -L` on the kiosk to find it). Empty means no real
        scanner is configured — SaneAirscanScanner will refuse to scan."""
        try:
            return self.get('SCANNER_DEVICE', str)
        except KeyError:
            return ""

    @property
    def scanner_dpi(self) -> int:
        try:
            return self.get('SCANNER_DPI', int)
        except KeyError:
            return 200

    @property
    def scanner_colour_default(self) -> bool:
        """Whether a scan session starts in Colour (SCANNER_MODE=Color). The default is
        Gray, which scans about twice as fast; the scanner screen lets the customer switch."""
        try:
            return self.get('SCANNER_MODE', str).strip().lower() in ('color', 'colour')
        except KeyError:
            return False

    @property
    def scanner_timeout(self) -> int:
        try:
            return self.get('SCANNER_TIMEOUT', int)
        except KeyError:
            return 60

    @property
    def sim_scanner_dir(self) -> str:
        """Directory holding SimScanner's canned page images when SIM_MODE=true."""
        try:
            return self.get('SIM_SCANNER_DIR', str)
        except KeyError:
            return "SSP/database/sim_scanner_pages"

    @property
    def sim_scanner_page_count(self) -> int:
        try:
            return self.get('SIM_SCANNER_PAGE_COUNT', int)
        except KeyError:
            return 3

    # Admin Dashboard (SSP/admin_dashboard) — separate FastAPI/Uvicorn
    # process from the Wi-Fi portal, see
    # docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md.

    @property
    def admin_dashboard_port(self) -> int:
        """Port the dashboard's own Uvicorn instance listens on — distinct
        from the Wi-Fi portal's port so the two processes never collide."""
        try:
            return self.get('ADMIN_DASHBOARD_PORT', int)
        except KeyError:
            return 8100

    @property
    def admin_dashboard_secret_key(self) -> str:
        """Secret used to sign the dashboard's login session cookie. Override
        before deploying to a real kiosk — this default is dev-only."""
        try:
            return self.get('ADMIN_DASHBOARD_SECRET_KEY', str)
        except KeyError:
            return "dev-insecure-secret-change-me"

    @property
    def admin_dashboard_session_hours(self) -> int:
        """Sliding inactivity timeout (hours) for a dashboard login session —
        any authenticated request resets the countdown."""
        try:
            return self.get('ADMIN_DASHBOARD_SESSION_HOURS', int)
        except KeyError:
            return 10

    @property
    def admin_dashboard_lockout_minutes(self) -> int:
        """How long a dashboard account stays locked after 5 consecutive
        failed login attempts."""
        try:
            return self.get('ADMIN_DASHBOARD_LOCKOUT_MINUTES', int)
        except KeyError:
            return 15

    @property
    def scan_upload_dir(self) -> str:
        """Directory scanner-composed PDFs are copied to before being handed
        to SessionManager for the scan-to-Wi-Fi/email redeem flow."""
        try:
            return self.get('SCAN_UPLOAD_DIR', str)
        except KeyError:
            return "SSP/database/scan_uploads"

    @property
    def scan_digital_fee(self) -> float:
        """Default flat fee (₱) for the digital copy of a scan (download/email).
        Kiosk Admin can override it via the 'scan_digital_fee' setting; see
        managers/digital_fee.py."""
        try:
            return self.get('SCAN_DIGITAL_FEE', float)
        except KeyError:
            return 5.0


# Global configuration instance
config = Config()


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Global Config object with loaded settings
    """
    return config
