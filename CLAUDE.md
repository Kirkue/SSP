# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run everything from the **repo root** (`SSP-Plus/`), not from `SSP/`:

```bash
make test      # pytest tests/ -v  (~400 tests, no hardware/DB required)
make test-hotspot   # hotspot firewall/dnsmasq checks in a Linux container (needs Docker)
make lint      # flake8 SSP/ scripts/  (config in .flake8)
make run-sim   # launches the GUI with SIM_MODE=true (no GPIO/CUPS/modem needed)
make run       # launches the GUI against real hardware (kiosk only)
make run-admin-dashboard   # launches the Admin Dashboard (separate process, own port — see below)
make screenshots   # renders every screen to screenshots/<screen>.png as the 1920×1080 kiosk shows it
```

Run a single test: `python -m pytest tests/test_payment_algorithm.py::TestCalculateChangeBreakdown::test_mixed -v`

`make` auto-detects Python (falls back to `python3`, or the first Windows Python with `pytest` installed when invoked from WSL — see `Makefile`). Override with `make PYTHON=/path/to/python test`.

First-time setup: `cp .env.example .env` and set `SIM_MODE=true` for laptop development. `.env` **must live at the repo root** — `config.py`'s `Config` class resolves it relative to the process's working directory (`.env` by default), and both Makefile targets invoke `python SSP/main_app.py` from the repo root. Running `main_app.py` directly from inside `SSP/` will fail because `.env` isn't there. If `.env` is missing, `config.py` calls `sys.exit(1)` immediately.

SIM_MODE (set via `.env` or as a shell var, which takes precedence — see `make run-sim`) disables GPIO, the CUPS printer submission, and the GSM modem, replacing them with console-logged simulation. It also makes `USBFileManager.get_usb_drives()` (`managers/usb_file_manager.py`) report a fake USB drive instead of doing real OS-level detection, so the `usb` screen auto-navigates to `file_browser` without a physical drive — the fake drive is a local directory (`SIM_USB_DIR` in `.env`, default `SSP/database/sim_usb_drive`) auto-seeded with a placeholder PDF on first run.

## Architecture

### Screen navigation (MVC + QStackedWidget)

`PrintingSystemApp` (`SSP/main_app.py`) owns a `QStackedWidget` and navigates via `show_screen(screen_name)`. `SCREEN_MAP` maps name → index: `idle`, `usb`, `file_browser`, `printing_options`, `payment`, `admin`, `data_viewer`, `thank_you`. Always navigate through `show_screen()` — it calls `on_leave()` on the outgoing screen and `on_enter()` on the incoming one, and (except for `admin`/`thank_you`) redirects to `thank_you` with an error if paper is low (`paper_count <= 3`) or any CMYK cartridge is critically low (`<= 20%`).

Each screen under `screens/<name>/` follows MVC with three files:
- `controller.py` — wires view signals to model methods, calls `show_screen()` for navigation
- `model.py` — business logic, hardware interaction, data
- `view.py` — PyQt5 widgets and layout

Customer flow: `idle` → `usb` → `file_browser` → `printing_options` → `payment` → `thank_you`. `admin` and `data_viewer` are side-paths reached via a PIN dialog (`screens/dialogs/pin_dialog/`).

### Inactivity timeout

One timeout for the whole kiosk: `main_app.timeouts` (`managers/timeout_manager.py`), not a timer per screen. A screen declares a `timeout_policy()` on its controller (a `TimeoutPolicy`: seconds, the `action` to run on expiry, an optional `busy()` check, `warn`, `taps_reset`); `show_screen()` hands it over via `_enter_timeout()`. No `timeout_policy()` means no timeout and no label: `idle`, `thank_you`, `admin`, `data_viewer`. The "Remaining Time" label and the expiry read the same deadline, so they can't drift apart, and an expiry only acts if its screen is still the one showing (`_on_screen_timeout`).

Any tap anywhere restarts it (`ui/activity_filter.py`, an app-wide filter, so screens don't wire buttons to a timer); coins, bills and QR reads call `main_app.note_activity()`. With `TIMEOUT_WARNING_SECONDS` (15) left a modal "Still there?" prompt (`ui/timeout_warning.py`) offers `TIMEOUT_EXTEND_SECONDS` (30) more; on payment it says what happens to cash already inserted. A `busy()` screen never expires (payment while change is dispensing, the scanner mid-scan, homepage behind the PIN dialog). `voucher` (3 min) and `scan_result` (60 s) have fixed countdowns: no prompt, taps don't restart them.

Where an expiry goes: before a file is chosen (`homepage`, `usb`, `wifi`, `email`, `scanner`) back to `idle`; mid-flow (`file_browser`, `print_options`, `payment`, `scan_destination`) back to the `homepage`, with `main_app.end_session()` clearing the customer's temp files. Payment's cash still becomes a Voucher through `show_screen()`'s carried-credit redirect. `tests/test_timeout_manager.py` drives it on a fake clock.

### Voucher balance popup

"Check voucher balance" is a popup, not a screen (`screens/voucher_balance`, opened by `main_app.open_voucher_balance()` from the homepage and print options): a dimmed full-window overlay, so nothing underneath can be tapped, and any `show_screen()` closes it and wipes it. While it's open a Voucher QR read checks the balance rather than doing what the screen underneath would. A Voucher that checks out is kept for the session in `main_app.session_vouchers` (`managers/session_vouchers.py`); the payment screen lists those with their balance and a tap-to-apply button and never applies one by itself. They're cleared by `end_session()` and on every arrival at `idle`. A balance check shares the wrong-code lockout with payment (ADR 0003).

### Background threads

Two persistent `QThread` managers are started in `PrintingSystemApp.__init__` and stopped in `cleanup()`:
- `DatabaseThreadManager` (`managers/db_threader.py`) — serializes SQLite writes to avoid cross-thread conflicts
- `InkAnalysisThreadManager` (`managers/ink_analysis_threader.py`) — runs PDF ink analysis off the main thread

### Hardware integration

| Component | Manager | Library |
|-----------|---------|---------|
| Printer (CUPS) | `managers/printer_manager.py` + `managers/printer_thread.py` | `subprocess` (`lp`/`lpstat`) |
| Coin/bill acceptors | `managers/persistent_gpio.py` | `pigpio` (GPIO pulse counting) |
| Coin hoppers (change dispenser) | `managers/hopper_manager.py` (`ChangeDispenser`, `HopperController`) | `pigpio` |
| SMS alerts | `managers/sms_manager.py` | `pyserial` (AT commands to GSM modem) |
| QR reader (kiosk 2D reader) | `managers/qr_reader.py` | `pyserial` (USB serial, CR-terminated reads) |

The QR reader is on when `QR_READER_PORT` is set in `.env` (blank = off, typed codes only, and the screens' `ReaderHint` is hidden). Reads are
classified and decided in `managers/qr_reader.py` (`classify_payload`, `decide_qr_read`), then
`main_app._on_qr_read` acts on them via `open_session_files()` — the same path a typed OTP takes.
Accepting screens are idle, homepage, wifi and email (each has `show_qr_message()` for the reply).
A Voucher read (`V1:`) is handed to `payment` (`apply_voucher_code`) or, while the balance popup
is open over any screen (`main_app._qr_context`), to the popup (`check_voucher_code`); both ignore
every other read, and all other screens ignore reads silently.
A payload read again within 3 s of its last accepted read is dropped, even with other reads in
between (`DuplicateReadFilter`; the reader's own duplicate time can't be set over serial). On
every port open `QrReaderManager` first re-sends the reader's settings as `#<code>;` (`KIOSK_CONFIG`, ~8 s; reads during it are held until it ends); NAKed or unanswered codes write one
`error_log` row per open. In `SIM_MODE`, Ctrl+Shift+Q opens a box to inject a payload. If the
reader is unplugged or fails to open, `QrReaderManager` goes `unavailable`, retries every 5 s and
resumes on its own; each loss and recovery writes one `error_log` row (`QR Reader`), and Kiosk Admin
shows the status (blank port = "Not configured"). See ADR 0004.

`pigpio` requires the `pigpiod` daemon. With `SIM_MODE` off, `main()` refuses to start if either is missing (`managers/gpio_check.py`), so a kiosk can never show customers the payment screen's simulated coin/bill buttons; those buttons appear only when `SIM_MODE=true`. The GPIO managers' own simulated fallbacks remain for SIM_MODE and tests. Pi install steps: "pigpio (kiosk)" in `docs/SETUP.md`.

**`managers/payment_handler.py` is dead code.** Nothing imports it; `screens/payment/model.py` wires up `managers/persistent_gpio.py`. If you're changing acceptor behavior, edit `persistent_gpio.py`, not `payment_handler.py`.

Acceptor and hopper pins come from the kiosk model: `KIOSK_MODEL` in `.env` (`old`, the default, or `new`) picks a pin set from `KIOSK_MODEL_PINS` in `config.py`. Any of `COIN_PIN`, `COIN_INHIBIT_PIN`, `BILL_PIN`, `BILL_INHIBIT_PIN`, `HOPPER_A_SIGNAL_PIN`, `HOPPER_A_ENABLE_PIN`, `HOPPER_B_SIGNAL_PIN`, `HOPPER_B_ENABLE_PIN` set in `.env` overrides the model's value (`tests/test_kiosk_model_pins.py`). The startup `Coin acceptor (...)` line names the model. The idle/payment controllers' "manual disable" backups and `main_app`'s startup disable still hardcode inhibit pins 22/23 (the same on both models).

The `new` model differs in coin input GPIO 17 and swapped hopper sensors (A on 26, B on 9), confirmed on that kiosk by GPIO scan (2026-10-22). Check a kiosk's real wiring with `scripts/gpio_scan.py` (on the kiosk, app stopped: `baseline`, `coins`, `hopper A|B`, and `empty A|B` to run a hopper until Ctrl+C), which counts low pulses on every non-output GPIO. The `old` model's pins, found that way:
- Coin acceptor input: GPIO 12; inhibit (active high, HIGH=enabled): GPIO 22
- Bill acceptor input: GPIO 18; inhibit (active low, LOW=enabled): GPIO 23
- Hopper A (₱1 coins): coin-out sensor GPIO 9, enable GPIO 24 (active low)
- Hopper B (₱5 coins): coin-out sensor GPIO 26, enable GPIO 25 (active low)

The coin line is noisy (sub-millisecond spikes even with no coin). With `COIN_PULSE_FILTER=true` (default) `PersistentGPIO` sets a pigpio glitch filter (`COIN_GLITCH_FILTER_US`) and counts only low pulses `COIN_PULSE_MIN_MS`–`COIN_PULSE_MAX_MS` wide; `false` falls back to falling-edge counting with a 0.1 s debounce, for checking the wiring alone. Pulse counts that match no coin are logged (`Coin ignored`) instead of dropped silently (`tests/test_persistent_gpio_coin_filter.py`). The bill line gets the same treatment (`BILL_PULSE_FILTER`, `BILL_GLITCH_FILTER_US`, `BILL_PULSE_MIN_MS`–`BILL_PULSE_MAX_MS`, default 20–150 ms): it carries sub-0.1 ms spikes in and between bills, which used to add pulses (a ₱50 read as 7, a ₱100 as 13, two stray spikes as a ₱20); real bill pulses are ~50 ms. Unmatched counts log `Bill ignored` (`tests/test_persistent_gpio_bill_filter.py`).

The hopper sensor lines pick up motor noise too, so `HopperController` sets a 5 ms glitch filter and counts a coin as one low pulse 20–300 ms wide (43–183 ms measured). A coin the sensor doesn't see within `DISPENSING_TIMEOUT` (1.5 s, the hoppers pay ~5 coins/s) stops that hopper with no retry, so an empty or jammed hopper, or a sensor that never registers coins, lets out a few coins at most and the rest of the change becomes a Voucher (`tests/test_hopper_controller.py`). From auto-complete until the change is out, the payment screen ignores Back and defers its timeout (`PaymentModel.is_busy()`), since leaving stops the hoppers. pigpiod keeps a motor's enable pin low after the app exits, so `main_app` stops both motors (`stop_all_hopper_motors()`) at startup and first thing in `cleanup()`, after ending any payout. A credited coin or bill restarts the payment screen's 60 s timeout.

### Database

SQLite at `SSP/database/ssp_database.db` (path is derived from `models.py`'s own location, so it's stable regardless of CWD — unlike `.env`). Schema is created by `database/models.py:init_db()`, called once at startup from `main()`. Tables: `transactions` (has a `source` column, see Admin Dashboard below), `cash_inventory`,
`error_log`, `printer_status`, `cmyk_ink_levels`, `settings`, `sessions`, `email_intake_log`,
`users`, `dashboard_login_log` (the last two are Admin Dashboard accounts/login-audit, unrelated
to the touchscreen's own `ADMIN_PIN`).

`main_app` writes two kiosk-liveness facts to the `settings` table for the Admin Dashboard to read
(`managers/kiosk_status.py`, issue #42): `kiosk_last_seen` (an ISO 8601 heartbeat, written at
startup and refreshed ~every 60 s by a `QTimer`) and `qr_reader_status` (the same one-line text
Kiosk Admin shows — `describe_reader_status`: "Connected"/"Not connected"/"Not configured"/
"Starting" — written at startup and on every reader status change). Both go through
`DatabaseThreadManager.update_setting` (the QR write fires on the reader thread); a failed write is
logged and never disturbs the kiosk.

All DB access goes through `DatabaseManager` (`database/db_manager.py`). Writes triggered from non-main threads must go through `DatabaseThreadManager` (`db_threader`) to avoid SQLite's same-thread restriction.

### Admin Dashboard (`SSP/admin_dashboard/`)

A separate, authenticated FastAPI/Uvicorn process for kiosk revenue reporting — sibling to
`SSP/webapp/` (the Wi-Fi portal), never started by `main_app.py` or `WebAppThreadManager`.
Start it with `make run-admin-dashboard`; it runs on its own port (`ADMIN_DASHBOARD_PORT`,
default 8100, distinct from the Wi-Fi portal's 8000) so a bug or compromise in the low-trust,
unauthenticated portal can never become a path into this DB-write-capable surface.

Auth is individual accounts in a `users` table, Argon2id-hashed passwords, two roles: `admin`
(full read/write) and `operator` (read-only), both unrelated to the touchscreen's
`Kiosk Admin`/`ADMIN_PIN`. The session cookie carries only the username; the role is read from
`users` on every request. `database/models.py`'s `migrate_dashboard_roles` renamed the original
`dev`/`admin` roles once, guarded by a settings marker. Accounts are created and passwords reset only via
`admin_dashboard/cli.py`, run by hand on the kiosk — no self-service signup or reset flow.
Login issues a signed cookie session with a 10-hour sliding inactivity timeout
(`ADMIN_DASHBOARD_SESSION_HOURS`); 5 consecutive failed attempts locks the account for
`ADMIN_DASHBOARD_LOCKOUT_MINUTES`; every attempt (success or failure) is written to
`dashboard_login_log`.

`/accounting` (HTML) and `/accounting/data?range=today|week|month|all` (JSON) show per-Source
(`usb`/`wifi`/`email`/`scanner`) revenue and transaction-count aggregates via
`DatabaseManager.get_accounting_summary()` — a `scanner`-sourced row only exists when the scan's
destination was print (a Photocopy) and/or a paid Digital Copy (`copies` = 0 when it's the
Digital Copy alone). The scan's digital copy (download/email) costs a flat fee
(`managers/digital_fee.py`: Kiosk Admin's `scan_digital_fee` setting, else `SCAN_DIGITAL_FEE`),
and nothing is delivered before payment: `scan_destination` routes print-only to
`printing_options`, print + digital to `printing_options` with the fee added, and digital-only
straight to `payment` (`print_job: False`). `PaymentModel._prepare_digital_copy()` creates the
session once paid, then `scan_result` shows the OTP (before `thank_you` starts the print); a
failed session becomes a refund Voucher. Both also carry `vouchers`: change dispensed and Voucher value issued / Applied
summed from the same completed transactions (`get_change_and_voucher_totals()`), plus the
outstanding Voucher liability — remaining value of unexpired Vouchers as of now, ignoring the
filter (`get_voucher_liability()`). `/paper-reset` (the SMS fuzzy-match reset fallback) is `admin`-only.
Real transactions get their `source` value from `screens/print_options/controller.py`'s
`self.source` (set per intake screen — usb/wifi/email/scanner controllers all call
`set_pdf_data(..., source=...)`), carried through `payment/model.py`'s `transaction_data` dict
into `DatabaseManager.log_transaction`, which persists it to `transactions.source`.

Demo/fixture data for developing the dashboard's visuals lives in a completely separate,
`SIM_MODE`-gated SQLite file (`SSP/database/ssp_database.sim.db`), populated by
`admin_dashboard/seed_demo_data.py` — the real `ssp_database.db` is never touched by it.

Tests (`tests/test_admin_dashboard.py`) drive `admin_dashboard.main:app` in-process via
`fastapi.testclient.TestClient`, overriding only the `get_db` dependency (pointed at a temp
SQLite file) — auth, sessions, lockout, role-gating, and aggregate queries all run through
real HTTP requests against the real app, no mocked business logic.

See `docs/adr/0002-admin-dashboard-auth-and-remote-access-architecture.md` and CONTEXT.md's
"Admin Dashboard" glossary section for the full design and rationale.

### Configuration

All runtime config comes from `.env` via `config.py`'s `get_config()` (global `Config` singleton). `Config._load_env_file()` uses `os.environ.setdefault`, so a shell-exported var always overrides `.env` (this is how `make run-sim` forces `SIM_MODE=true` without editing `.env`). Accessing an unset key raises `KeyError` (see `Config.get`) — there are no silent defaults except `sim_mode`, which returns `False` if unset.

The touchscreen UI is laid out in fixed pixels for an ~800px-tall screen; `main()` scales all of it with Qt's `QT_SCALE_FACTOR`, set by `ui/scaling.py` from `UI_SCALE` (blank/`auto` = screen height ÷ 800, minimum 1; a number forces that scale). Keep every screen within 800 logical px tall (admin is ~768; wifi and email are ~704 with their QR, keypad and a status showing), or it overflows on the 1080-tall kiosk panel; `tests/test_screen_render.py` fails if one doesn't fit.

The UI renders the same however it's launched (desktop terminal, SSH, systemd, a laptop): `main()` calls `ui/scaling.py`'s `pin_render_environment()` first (on Linux forces `QT_QPA_PLATFORM=xcb` and drops the desktop's Qt theme/DPI variables), `apply_theme()` uses the Fusion style and the Inter font bundled in `SSP/assets/fonts/`, and the base font is sized in pixels, never points. Startup prints a `Render:` line (platform, screen, scale, DPI, font); two launches with the same line look the same. `make screenshots` (`scripts/render_screens.py`) is the reference picture for UI changes. Text sizes and colours come from `ui/theme.py`'s `FONT`/`COLORS` (smallest text 16px, body text semibold, secondary/muted greys at WCAG AA contrast); use those tokens rather than hardcoded px.

### Print job flow

1. `file_browser` (select file) → `printing_options` (set copies/color/pages) → `payment` (insert coins/bills)
2. `payment` model emits `payment_completed` → `main_app.on_payment_completed()` calls `printer_manager.print_file(...)`
3. `PrinterThread.run()` builds a temp PDF containing only the selected pages (via PyMuPDF/`fitz`), submits it to CUPS with `lp`, then polls `lpstat -l -p <printer>` for job completion, paper jams, and media-empty alerts (sends SMS on jam/no-paper via `sms_manager`). A `paused` alert (CUPS disabled the queue) fails the job, and `check_printer_availability()` refuses a `disabled` queue before submitting. The job counts as printed only once it has left `lpstat -o`, and this thread is the only thing that reports success: the thank-you screen just waits for its signals (`tests/test_printer_completion.py`)
4. Settlement happens before printing: once change is out, `PaymentModel.settle_transaction()` logs the `transactions` row as `paid` and updates `cash_inventory` (received coins added, dispensed change subtracted), once per `payment_ref`. The print outcome then moves the row (`managers/print_refund.py`): on success `completed` (and `main_app` decrements paper count, then triggers ink analysis); on failure `print_failed` plus one refund Voucher worth `total_cost` (shown on the voucher screen, `VoucherModel.REFUND`), and the CUPS job is cancelled. Only `completed` counts as revenue; `print_failed` still counts toward change dispensed / Vouchers Applied (issue #59). A paid Digital Copy that can't be made is refunded as a Voucher for the fee (`record_digital_refund`): a digital-only sale ends as `digital_failed` (not revenue, counted like `print_failed` in the change/Voucher totals); with a print the row stays `paid` and only `voucher_issued` is updated
5. `InkAnalysisThreadManager` uses `pdf2image` + OpenCV on the temp PDF to estimate CMYK consumption and updates `cmyk_ink_levels`
6. The temp PDF is deleted only after ink analysis completes (`PrinterManager.cleanup_last_temp_pdf`), since analysis needs it even if the original USB drive was removed

### Payment logic

`PaymentAlgorithmManager` (`managers/payment_algorithm_manager.py`) calculates change feasibility from current ₱1/₱5 coin inventory and suggests payment amounts when exact change can't be made. Change dispensing only attempts the coins `cash_inventory` says the hoppers hold (`coin_limits`), as many ₱5s as possible then ₱1s, and a ₱5 hopper failure is topped up with ₱1s. Whatever doesn't come out is the Shortfall, which `payment/model.py` records in a per-payment `ShortfallOutcome` and labels `ShortfallCause.PREDICTED` (the inventory couldn't cover it) or `ShortfallCause.HOPPER_FAILURE` (a hopper stopped early) and turns into a Voucher (ADR 0003). Min coin thresholds and max change limits are configurable via the `settings` DB table. When `get_max_dispensable_change()` is below `low_change_warning_threshold` (`settings`, default ₱20), idle and the homepage show a low-change banner (re-checked on every `on_enter()`) and tapping through idle asks "Continue anyway / Cancel" (`tests/test_low_change_warnings.py`). The manager's unit tests (`tests/test_payment_algorithm.py`) are pure logic with a mocked `DatabaseManager`. Cash put in without completing the payment is never dropped: `PaymentModel.on_leave()` keeps it as Carried Credit (`CarriedCredit`), restored by the next `on_enter()`; `main_app.show_screen()` calls `redirect_for_carried_credit()`, which, for any destination other than payment/printing_options, issues a Voucher for it, logs a `cancelled_partial_payment` row and shows the voucher screen first (its `on_continue` goes on to the destination; nothing prints). See ADR 0008. The dispense → Shortfall → Voucher path is covered end to end in SIM_MODE by `tests/test_payment_change_flow.py` (real models and `DispenseThread`, offscreen `VoucherController`, temp SQLite).

## Workflow

`main` is protected — PRs require one review before merge. Branch as `feature/<module>`. Hardware-dependent PRs (GPIO, printer, SMS) need a confirmed run on actual kiosk hardware before merge, since `make run-sim`/CI only exercise the simulated paths.

Commit trailers: a `Co-Authored-By:` line is fine. Never add a `Claude-Session:` trailer or any other link to a chat or session. Those links are private and mean nothing to reviewers.

## Agent skills

### Issue tracker

Issues live as GitHub issues in ku-ro-wa/SSP-Plus, via the gh CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root CONTEXT.md + docs/adr/. See `docs/agents/domain.md`.
