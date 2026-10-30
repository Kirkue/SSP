# Remaining Work

Living triage list. Update status, add notes, and move items between phases as decisions land.

**Status key:** `todo` · `needs-disc` (needs a decision first) · `decided` (see Discussion notes) · `needs-measuring` · `needs-supervisor` · `blocked` (waiting on someone or something outside the team) · `in-progress` · `done`

---

## Phase 1: Quick wins (now)

Small, well-defined changes. None need a decision, so they can be done in parallel.

| #   | Item                                                                              | Status     | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --- | --------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.1 | Change the banner colour to a shade of green                                      | done (stc) | Supervisor's request. Not too light: somewhere between Chime and Instacart green, or a darker pastel. The banner is the `Header` widget (`SSP/ui/widgets.py`), styled by `HEADER_QSS` in `SSP/ui/theme.py`. It's currently charcoal (`COLORS["text"]`) with white text, so the green must keep white text readable (≥4.5:1 contrast). Bright Chime-style greens fail that, so lean darker. Also decide whether the banner should match `COLORS["primary"]` (`#2F7D5C`, already a muted green) or differ from it so the buttons still stand out. Candidates: `#2F7D5C` (current primary), `#3B8C66`, `#2E8B57`. |
| 1.2 | Add the admin button to the homepage, not just the idle screen                    | done       | Reuse the idle screen's existing entry point and auth.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 1.3 | Make the `screens/scan_destination/` preview match the `screens/scanner/` preview | done       | Cosmetic and layout parity only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 1.4 | Make the price breakdown on the payment screen more UX-friendly                   | done       | Cosmetic. Make sure the flat digital-copy fee from the latest commit still displays clearly.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 1.5 | Fix admin page column scaling so messages aren't cut off                          | done       | Options: word-wrap, tooltip, or a resizable or stretch-last column.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

## Phase 2: Needs discussion (decide soon, build next)

Each item needs a team or supervisor decision before work starts. The questions are listed so the discussion stays short.

| # | Item | Status | What the code does today | Open questions |
|---|------|--------|--------------------------|----------------|
| 2.1 | Timeout control: a global "add time" button and/or pausing the timer on sensitive screens (e.g. mid-payment) | in-progress (code done on `feature/phase-2`, needs a kiosk run) | Two separate mechanisms. Each screen's own `QTimer` (60 s) does the actual navigation. `main_app.start_global_countdown()` only drives the "Remaining Time" label. They can disagree: payment restarts its own timer on every coin, bill, or voucher keystroke but never restarts the label. A payment timeout already turns inserted cash into a Voucher (ADR 0008, Carried Credit). It's deferred while change is dispensing (`is_busy()`). So no money is lost on timeout. | Is the pain point the timer's length, or that customers don't see it coming? An "add time" prompt near the end (e.g. "Still there? +60 s" at 15 s left) avoids pausing completely. A single timer owned by `main_app` would fix the label drift and make "add time" a single change. |
| 2.2 | Add the "check voucher balance" button to the print options and payment screens, and allow QR scans to check a balance | in-progress (code done on `feature/phase-2`, needs a kiosk run) | QR balance checks already exist: `qr_reader.py` maps a `V1:` read on `voucher_balance` to `check_voucher`, and on `payment` to `apply_voucher`. "Scanned once" is most likely `DuplicateReadFilter`, which drops the same payload for 3 s, plus the reader's own duplicate detection. It isn't a hardware limit. Leaving the payment screen for anywhere except print options abandons the payment, and the Carried Credit becomes a Voucher (CONTEXT.md). | A balance button on the payment screen can't navigate to `voucher_balance` without abandoning the payment. Should it be a dialog on top of the screen instead? On the payment screen a QR read *applies* the voucher, so does a balance check there need its own mode, or is "apply, see what it covered, remove" enough? |
| 2.3 | Scanning speed (~19 s on the new kiosk), possibly with upscaling or de-noising | in-progress (code done on `feature/phase-2`, needs a kiosk run) | `scanimage --format=png --mode=Color --resolution 200` over eSCL (`SCANNER_DPI=200`). We do no post-processing. Pages are combined into a PDF with PyMuPDF only at `finish()`. | Is the 19 s per page or per session? Time `scanimage` by itself on the Pi to separate the scanner's time from ours. Cheap options to try: `--mode=Gray` for documents, and a lower DPI. Upscaling and de-noising add time, so they work against the speed goal. |
| 2.4 | More robust PDF checks on the Wi-Fi and email pathways, matching the USB pathway | done (on `feature/phase-2`) | The premise looks backwards. USB only checks the `.pdf` extension and falls back to `pages = 1` if PyMuPDF can't open the file (`usb_file_manager.py`). Wi-Fi checks MIME type, size, empty file, and the `%PDF` header. Email checks size and the `%PDF` header, and takes only the first PDF attachment. | Which checks did we have in mind? A likely answer is one shared validator for all sources: header, opens in PyMuPDF, not encrypted, page count > 0, size limit. It would run after download, so email isn't harder than the rest. Should a broken file be rejected at upload or flagged at the file browser? |
| 2.5 | Ink and paper level tracking | in-progress (code done on `feature/phase-2`, needs a kiosk run) | Already estimated in the DB, as `printer_status.py` explains. The Smart Tank reports paper-out, jams, and an open door, but no sheet count or ink levels. Paper is a software counter decremented on each print. Ink is estimated from page coverage (`ink_analysis_manager`). Both are reset by an admin on refill. | So this is about accuracy and the refill workflow, not missing tracking. Where does it go wrong in practice: refills not recorded, or estimates drifting? Could a paper-out alert from the printer auto-correct the counter? |
| 2.6 + 2.7 | Unify the admin screen and the dashboard; reconsider Tailscale | needs-supervisor | **Already decided, as a pair, in ADR 0005.** Kiosk Admin moves into the Admin Dashboard as `/kiosk` and `/logs` pages (release 1 view-only, release 2 edits plus an audit log), served remotely via Tailscale Serve. Not built yet: `admin_dashboard/routers/` has only `accounting` and `auth`. The heartbeat from #87 is part of it. | Is ADR 0005 still the plan, given the supervisor set Tailscale aside? Without Tailscale, the unified dashboard is only reachable on the kiosk itself, which removes most of its value. The case to bring to the supervisor: the ADR, the dedicated project tailnet, and "never public". |

### Discussion notes

**2.1 (timeout):**
- Why it matters: during testing we get sent home while hunting for a specific denomination to test change/acceptance. Real users would find that confusing. The timer is also easy to miss.
- Direction: a "Still there?" prompt near the end that adds time. Make the amount a config setting (default +30 s?).
- **Decided:**
  - **One timeout manager in `main_app`** replaces the per-screen `timeout_timer`s and the separate countdown label. The label reads from the same timer, so the two can't drift.
  - **Each screen declares a policy:** a duration, what happens when the timer runs out, and an optional "not now" check. For example, payment refuses to time out while change is dispensing.
  - **Any tap counts as activity.** An app-wide event filter catches taps, like `ui/tap_guard.py`. Coin, bill, and QR events also count.
  - **A "Still there?" warning** appears with N seconds left and offers +X seconds. Both are `.env` settings, e.g. `TIMEOUT_WARNING_SECONDS=15` and `TIMEOUT_EXTEND_SECONDS=30`.
  - **On payment, the warning says what happens to cash already inserted.** For example: "Your P20 will be saved as a voucher."
  - **Where timeouts go:**
    - Before a file is chosen (homepage, usb, wifi, email, scanner): idle.
    - Mid-flow (file_browser, print_options, payment, scan_destination): homepage.
  - **Screens that already move on by themselves keep doing so:** thank_you, voucher, scan_result. The label must show their real countdown, or be hidden.
  - **Admin and data_viewer: no timeout and no label.** Logging out is the admin's responsibility.
- Still to confirm when building:
  - The default values for N and X.
  - A mid-flow timeout must still clear the session's files. USB files and uploads shouldn't be left for the next person.
  - ~~Whether the payment timeout still goes through the screen that shows the Carried Credit Voucher code.~~ Yes. `show_screen()` calls `redirect_for_carried_credit()`, so the timeout keeps working as long as it goes through `show_screen()`.
- How timers work today:
  - Each screen controller owns a single-shot `timeout_timer`, restarted only by signals it explicitly connects to `_reset_timeout`. A tap anywhere else doesn't count as activity.
  - `main_app.show_screen()` separately starts a 60 s "Remaining Time" label on every screen except idle. It's for display only: it hides itself at 0 and does nothing.
  - The screen's timer and the label are independent, so they drift apart:
    - Homepage, USB, and payment restart their timer but not the label.
    - Admin and data_viewer have no timer at all, but show a label that counts to 0.
    - Thank_you shows 60 s but redirects after 5 s (done), 10 s (no printer), or 120 s (safety).
  - Destinations aren't consistent: some screens time out to idle, others to homepage. Scan_result "times out" by continuing to the paid print.
  - Special cases: payment defers its timeout while change is dispensing, and the voucher screen uses 180 s.

**Parked, come back to these:**

**2.6 + 2.7 (dashboard remote access):**
- Scope: **(a)** each kiosk runs its own dashboard, and admins reach it from their own phone or laptop. This is ADR 0005's model. A central server (b) stays deferred.
- The open question is only how admins reach it. Options:

| | Tailscale + Serve (ADR 0005) | Cloudflare Tunnel + Cloudflare Access | On-site only (no remote) |
|---|---|---|---|
| Admin device setup | Install the Tailscale app and sign in. The VPN must be on when checking (on iOS, only one VPN can be on at a time). | Nothing to install: open `admin.<domain>`, log in with an email code or Google | Be on the kiosk's network or touchscreen |
| Kiosk setup | `tailscale up` + `tailscale serve`, once | `cloudflared` tunnel + an Access policy | None |
| Cost | Free Personal plan (limits on user and device count; *verify current limits*) | Zero Trust free tier (user cap; *verify*) + a domain (about $10/yr, already needed by ADR 0006) | Free |
| Exposure | Not reachable from the internet at all. Only tailnet devices can reach the login page. | Reachable from the internet, but Cloudflare checks the login before any traffic reaches the Pi. A mistake in the Access policy exposes the dashboard, with only its own login left as protection. | None |
| Fits the ADRs? | Yes (ADR 0005) | Breaks ADR 0005's "never public" limit. ADR 0006 deliberately keeps admin access on different software from public access. | Drops the remote half of ADR 0005 |
| More kiosks | Each kiosk joins the tailnet and appears by name. Tags/ACLs are already planned. | One hostname and Access app per kiosk, which can be scripted | n/a |
| Router / CGNAT | Outbound only, works anywhere | Outbound only, works anywhere | n/a |

- Rejected outright: port forwarding or DDNS (needs control of the router, fails behind CGNAT, and is public), and self-hosted WireGuard (needs a public server to maintain).
- **Context from discussion:**
  - The supervisor probably set Tailscale aside over complexity or installing the app. The main features are now mostly built, and the PCB work means we're designing for replication, so now is a good time to revisit.
  - Admins are our team for now. Later the supervisor wants to make kiosks **rentable**, and each operator should see their own kiosk and how it's performing.
  - The supervisor rejected buying a domain ("additional cost to the operator").
- **Recommendation: Tailscale (keep ADR 0005).** With no domain, the Cloudflare option is gone, and Tailscale is the remote option that costs nothing.
- **How to pitch it to the supervisor:**
  - **No cost to the operator:** no domain (the `*.ts.net` name comes with it), no router setup, and the free plan.
  - **Little complexity per kiosk:** the setup script joins the kiosk to the tailnet with a pre-auth key that already carries `tag:kiosk` and `tag:site-<KIOSK_ID>`, then runs `tailscale serve`. It's part of the same reproducible build as the PCB, not a manual step.
  - **Operators** install one app and open a bookmark. That can be a step in the rental onboarding kit.
  - **For rentals:** keep the tailnet on the project or business account (ADR 0005). Give each operator access to **only their kiosk**, either by sharing the device into their own free Tailscale account, or with ACLs on the already-planned tags. Sharing may not use up a user slot on our plan. *Verify both the current free-plan limits and how sharing is counted.*
  - **It keeps the central view open:** a future fleet dashboard (option b) can join the same tailnet and pull data from each kiosk. Nothing needs redoing.
- **Knock-on effect for ADR 0006:**
  - The domain rejection also blocks the planned public upload address (`print.<domain>` via Cloudflare Tunnel).
  - Counter-argument for the supervisor: ADR 0006 uses **one domain for the whole fleet** (`print.<domain>/k/<KIOSK_ID>`), so it's about $10 a year for the rental business, not a cost for each operator.
  - Raise it separately, since it's a different feature.

**2.4 (PDF checks):**
- `feature/unreadable-pdf` (b6a13c2) adds `managers/pdf_check.check_pdf()`. A file passes if it opens, isn't password-protected, has at least one page, and every page loads. Both `USBFileManager` copy paths record the reason a file fails, and file_browser blocks it.
- Wi-Fi and email files already go through one of those paths: `main_app.open_session_files()` → `scan_and_copy_pdf_files_by_paths()`. **Once the branch is merged, all three sources get the same check at the file browser.** Nothing about email makes this harder.
- **Decided:** yes, Wi-Fi also runs `check_pdf()` at upload, so the customer learns about a bad file on their phone.
- Original question: should Wi-Fi also run `check_pdf()` at upload? That would tell the customer on their phone, before they walk to the kiosk. Email can't easily give that feedback (it would need a reply email), so email files keep the file-browser check only.

**2.2 (voucher balance):**
- The voucher balance screen never tells users they can scan their QR code. Fix the wording on it.
- **Print options: the balance check is a popup, not a screen change.** Leaving the screen is technically safe, but customers don't know that. A popup also adds less friction.
- **Payment: no separate balance check.** Vouchers already checked are shown with their amounts instead.
- **Decided:**
  - **One global "Check voucher balance" popup** is used everywhere: homepage, print options, and anywhere else that offers a balance check. It replaces the `voucher_balance` screen, which can then be removed.
  - **Vouchers checked in the popup are remembered for the session** and listed on payment with their balance and a tap-to-apply button. They're never applied automatically.
  - **The remembered vouchers are cleared along with the session's files** (timeout or session end).
  - **While the popup is open, a QR voucher read checks the balance** and doesn't apply it. Closing the popup restores the screen's normal QR behaviour (`qr_reader.decide_qr_read`).
- Today, applied vouchers already show on payment as "Voucher: P_ applied, P_ left" (`payment/view.py` `update_vouchers`).

**2.5 (ink and paper estimates):**
- The risk is false flags either way: blocking prints when supplies are fine, or allowing them when supplies are out.
- **How paper works today:**
  - It's a DB counter, decremented by `selected pages × copies` only after a successful print (`main_app._update_paper_count_after_print`).
  - Print options blocks a job that needs more sheets than the counter says are left.
  - `show_screen()` blocks every customer screen at ≤3 sheets.
  - The printer's own paper-out alert (`media-empty`/`media-needed` in `printer_thread.py`) fails the job and sends an SMS, but **doesn't correct the counter**. The counter can say 40 sheets while the tray is empty, and the next customer pays and then fails.
- **How ink works today:**
  - Each printed job is rendered, its CMYK coverage is estimated (`ink_analysis_manager.py`), and a share of the tank is subtracted. `show_screen()` blocks every customer screen when any colour drops to ≤20%.
  - Problems found:
    - **The yields are hardcoded at 17,000 pages for both black and colour** (`_calculate_job_costs`), whatever the printer model, and can't be configured. If the real bottle yield is lower, the estimate drains far too slowly and shows ink left when the tank is dry. Smart Tanks don't error when empty; they just print faded.
    - **Coverage counts only non-white pixels** (`ignore_white=True`), so it overestimates. On our two test PDFs, black coverage came out at 7.3% vs. 5.0% and 10.7% vs. 6.7% for the whole page, about 1.5×.
    - **Colour is drained as one pool.** The combined C+M+Y cost is subtracted from each of C, M, and Y, so a cyan-only job drains yellow too.
    - The 20% and 3-sheet thresholds are hardcoded.
    - "Refill" implies resetting to 100%, but tanks are topped up from bottles and are often only partly full.
- **Decided:**
  - **Paper:** when the printer reports `media-empty` or `media-needed`, set the counter to 0. The kiosk then stops taking customers until a refill is recorded.
  - **Paper:** keep the low-paper operator alert at about 10 sheets, but accept that the counter is approximate. The printer's paper-out report is the backstop.
  - **Ink:** low ink **alerts the operator** (SMS and the dashboard) and never blocks customers by itself. Customers are blocked only when an admin marks a tank as empty. Customers can't see the tanks inside the enclosure, so only the operator can check them.
  - **Ink:** the admin enters the tank level they see. "Refill to 100%" stays only as a SIM_MODE convenience.
  - **Ink:** bottle yields become `.env` settings, set for the current printer.
- Found while checking: the low-paper threshold was **not** configurable. It was hardcoded `10` in both `main_app.py` and `screens/admin/model.py`, each with its own "alert sent" flag. (`main_app`'s copy only printed, so it never sent a second SMS; the real duplicate was a paper-out sending both the out-of-paper SMS and the generic print-failure one.) Now one `.env` setting, `LOW_PAPER_ALERT_SHEETS`, checked in `AdminModel.check_low_paper_alert`.
- **Printer history:**
  - The kiosk first had an HP Smart Tank 580-590 (USB + ipp-usb, queue `HP_Smart_Tank`, PR #74). Scans took about 17 s per page.
  - On 2026-10-20 it was swapped for the **HP Smart Tank 660-670**: queue `ipp://localhost:60000/ipp/print`, `SCANNER_DEVICE=escl:http://localhost:60000` (PR #81). Scans take about 20 s per page.
  - The two models scan at a similar speed, which suggests the scan time is mostly the scanner hardware and eSCL. The 2.3 measurements will confirm.
- **To do:** look up the 660-670's official bottle yields on HP's spec sheet (black and per-colour) and use them as the `.env` defaults. From memory, they're GT53/GT53XL black and GT52 colour bottles, but don't rely on that.
- **Paper-out reporting, measured on the kiosk (2026-10-30, `ipptool get-printer-attributes` on `ipp://localhost:60000/ipp/print`, HP Smart Tank 660-670):**
  - Tray out, no job sent: identical to tray in. `printer-state=idle`, `printer-state-reasons=none`, `media-ready=iso_a4_210x297mm`. The printer doesn't notice a missing tray until it tries to feed.
  - Tray out, job sent: `printer-state=processing`, `printer-state-reasons=spool-area-full-report` (not `media-empty`/`media-needed`), `media-ready` disappears, and `printer-alert-description` contains `Out of Paper` with `severity=critical`.
  - Early snapshots (taken 5–10 s into a stuck job) suggested the `media-empty`/`media-needed` checks in `printer_thread.py` and `printer_status.py` never fire. **That was premature, see the longer watch below.** **CUPS doesn't show it either:** with a job stuck, `lpstat -l -p HP_Smart_Tank` (the app's queue) showed `idle` and `Alerts: none`. The auto-created `HP_Smart_Tank_660_670_series_1074DB_USB` queue showed `now printing` with `Alerts: cups-waiting-for-job-completed`, and its job showed `Waiting for job to complete` / `job-printing`. There was no media alert, so the app's `lpstat` polling can't see paper-out. Still to check: whether that changes after a minute, and what `printer_thread.py` does on a long timeout. The paper-out detection for "set the counter to 0" must use something that is actually present, such as `Out of Paper` in `printer-alert-description` or `media-ready` going missing during a job.
  - **Longer watch (2026-10-30, tray out, 5-page job on `HP_Smart_Tank`, polled every 4 s):** for ~30 s the printer reported `processing` / `spool-area-full-report`, with `Out of Paper` absent. Then it went `stopped` with `printer-state-reasons = media-empty-error,media-needed-error,spool-area-full-report` and `Out of Paper` present. At the same point `lpstat -l -p HP_Smart_Tank` listed `Alerts: cups-waiting-for-job-completed media-empty-error media-needed-error`, so CUPS does surface it after ~30 s, and those names match the `printer_thread.py` checks. After the job was cancelled the printer sat `idle` with `printer-state-reasons = media-empty-report` and no `media-ready` line. With paper loaded the printer was back to `idle` / `none`, `media-ready` returned and `Alerts: none`. A job sent then printed. A tray left slightly open paused the job, and it resumed by itself once the tray was closed (no app in the loop). Not checked: whether a half-closed tray raises `media-empty-error`. If it does, the app would fail and refund a job after ~30 s that could still have printed.
  - Consequence: the correction can only happen after a customer's job is sent, so the first customer after the tray empties still pays and gets a refund Voucher.
  - `marker-levels` reads 100,100,100,100 as four ink *cartridges* with a low level of 2. It stayed at 100 after about 10 pages of colour printing (a 3-copy job cut off partway). That is probably a placeholder, but 10 pages is well under 1% of a tank, so it isn't proof. Either way the app doesn't use it: the admin enters the level they see.
  - `lpstat -p` lists two queues. `HP_Smart_Tank` is the intended one (`lpstat -v`: `ipp://localhost:60000/ipp/print`, PR #81) and is what `PRINTER_NAME` should be. `HP_Smart_Tank_660_670_series_1074DB_USB` (`implicitclass://`) is created by CUPS itself, so don't use it and don't delete `HP_Smart_Tank`.
- Nothing has been flagged wrongly yet, because the kiosk hasn't been deployed. Revisit the yields after real use.

**2.3 (scanning speed):**
- It takes about 19 s for **one page** at 200 DPI, in colour, saved as PNG.
- The time splits into three parts:
  - the scanner hardware/firmware: carriage speed, which depends on DPI and colour mode;
  - eSCL/ipp-usb: job setup, warm-up, and transfer;
  - the Pi: `scanimage` re-encoding the page as PNG.
- Only DPI, colour mode, and output format are under our control.
- **Measured on the kiosk (2026-10-30, one A4 page on the glass, wall-clock):**

  | Run | Time |
  |---|---|
  | PNG, Color, 200 dpi (today) | 20.0 s |
  | JPEG, Color, 200 dpi | 18.2 s |
  | PNG, Gray, 200 dpi | 11.4 s |
  | JPEG, Gray, 200 dpi | 9.1 s |
  | PNG, Color, 150 dpi | 11.7 s |

  - Colour mode is what makes scans slow. Gray is about 43% faster at the same DPI, and lowering Colour to 150 dpi is no better than Gray at 200.
  - JPEG saves a steady ~2 s over PNG (encoding is a small cost, not the bottleneck).
  - **Decided:** default to Gray + JPEG at 200 dpi (~9 s). Offer Colour as an explicit option and show that it takes longer (~20 s). Whether most scans are greyscale is still unconfirmed, so ask the supervisor.
  - The scanner answers `Device busy` for a while after a scan, so back-to-back scans (e.g. "scan another page") must wait and retry.
  - `scanimage --progress` fails on this kiosk with "Document feeder out of documents" (a plain scan with the same options works), so progress can't be measured this way. Use estimated progress from recent scan times.
  - A `--mode=Gray` scan saved as PNG is typed `8-bit/color RGB`, but R==G==B on every pixel (checked), so the scanner did return real grey. Consider converting to true 8-bit grey before building the PDF to shrink the files.
- **Original plan (kept for reference):** run these on the kiosk with a page on the glass:

  ```bash
  D='escl:http://localhost:60000'
  time scanimage -d "$D" --format=png  --mode=Color --resolution 200 > /tmp/a.png   # today's settings
  time scanimage -d "$D" --format=png  --mode=Color --resolution 200 > /tmp/a2.png  # again right away: is warm-up a big part?
  time scanimage -d "$D" --format=png  --mode=Gray  --resolution 200 > /tmp/b.png
  time scanimage -d "$D" --format=jpeg --mode=Color --resolution 200 > /tmp/c.jpg
  time scanimage -d "$D" --format=png  --mode=Color --resolution 150 > /tmp/d.png
  scanimage -d "$D" --progress --format=png > /tmp/p.png   # does the percentage climb steadily or jump at the end?
  ```

  How to read the results:
  - All about the same: it's the hardware. Only lower DPI or grey helps.
  - JPEG clearly faster: our PNG encoding is the bottleneck. That's an easy code fix.
  - Grey clearly faster: offer a greyscale default.
- 200 DPI is fine apart from some corners. Upscaling and de-noising become an **optional post-processing step**, not the default.
- Most scans are probably greyscale, but that's unconfirmed. Possibly default to greyscale and offer a colour option. Decide after measuring.
- **Progress feedback:** the UI currently shows only static "Scanning..." text (`scanner/view.py` `show_status`).
  - `scanimage --progress` prints percentages to stderr. But eSCL sends the whole image only after the scan finishes, so real progress through sane-airscan probably jumps from 0 to 100 at the end. Verify on the kiosk.
  - If it does jump, show estimated progress based on how long recent scans took, plus an animation. A live preview of the page as it scans isn't possible over eSCL.
- **Ties into 2.1:** the screen must not time out while a scan is running. The scanner screen's "not now" check is that it's busy scanning.

## Phase 3: Blocked externally (track, don't schedule)

| # | Item | Status | Waiting on |
|---|------|--------|------------|
| 3.1 | PCB design for the kiosk circuit board (production) | blocked | The design. |
| 3.2 | Router for the Ethernet connection, plus a second PSU for power-draw issues | blocked | The supervisor buying the hardware. The PSU issue may affect stress testing (4.3). |
| 3.3 | Digital payment option | blocked | Dev API access (teammate is following up). |

## Phase 4: Pre-deployment hardening (once Phases 1–2 settle)

Do these roughly in this order. Each one feeds the next.

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4.1 | Codebase inspection | todo | Dead code, consistency, test gaps. Doing it first makes the audit easier. |
| 4.2 | System-wide security audit | todo | Admin auth, hotspot and portal exposure, file handling (malicious PDFs), `.env` secrets, remote access. |
| 4.3 | Stress test the kiosk: try to break it and find bugs | todo | Do this on final hardware if possible. Needs the PSU fix (3.2). |
| 4.4 | Move important system config to independent accounts | todo | Last step before handover. Any accounts or keys tied to personal accounts. |

---

## Changelog

- Initial version created from the brain-dump list.
- 1.1: added guidance on the shade of green and pointers to the theme code.
- Phase 2: added what the code does today for each item. Merged 2.6 and 2.7, since ADR 0005 decides them together.
- Phase 2 triage: 2.1, 2.2, 2.4 and 2.5 decided. 2.3 waits on measurements from the kiosk. 2.6 + 2.7: recommend Tailscale, pending the supervisor.
- 2.3: measured on the kiosk. Decided on Gray + JPEG at 200 dpi by default, with Colour as an option.
- 2.5: measured paper-out reporting. The printer only reports it after a job is sent, and not as `media-empty`/`media-needed`. The detection in the code needs changing.
- 2.2: built on `feature/phase-2`. The `voucher_balance` screen is gone: a full-window popup (`screens/voucher_balance`) opens from the homepage and print options, closes on any screen change, and shows the reader hint ("Hold your QR code up to the reader, or type your code.") when a reader is configured. While it's open a Voucher QR read checks the balance (`main_app._qr_context`). Checked Vouchers are kept in `main_app.session_vouchers` and listed on payment with a tap-to-apply button; never applied automatically; cleared by `end_session()` and on every arrival at idle. Payment has no balance button, as decided. Not verified on the kiosk: the popup on the real touch panel, and a real Voucher QR through the reader while it's open. The 3 s duplicate-read window still applies to a second scan of the same code.
- 2.1: built on `feature/phase-2`. One `TimeoutManager` in `main_app` replaces the 13 per-screen timers and the separate label. Screens declare a `timeout_policy()`; any tap (app-wide filter), coin, bill or QR read restarts it; a modal "Still there?" prompt at 15 s left adds 30 s (`TIMEOUT_WARNING_SECONDS`, `TIMEOUT_EXTEND_SECONDS`) and on payment says what happens to the cash; busy screens never expire; an expiry only acts if its screen is still showing. Destinations now follow the decision (pre-file to idle, mid-flow to homepage), and mid-flow expiries call `end_session()` to clear temp files. Not verified on the kiosk: the touch panel's real taps through the filter, the overlay on the 1080p panel, and your obscure early-redirect bug, which I didn't find in the old code by reading: check whether it still happens (the single deadline and the stale-expiry guard should rule out the per-screen-timer causes I could think of).
- 2.3: built on `feature/phase-2`: `scanimage` now runs Gray + JPEG at 200 dpi by default (`SCANNER_MODE=Color` flips the default), the scanner screen has a "Colour: off (faster)" toggle, a `Device busy` is retried for up to 10 s, and a progress bar is paced against the average of the last 5 scans of the same kind (9 s / 20 s until measured). To check on the kiosk: a Gray JPEG page's text sharpness (scanimage's JPEG quality isn't configurable here), the real time of a scan from the app, and that the preview loads the JPEG. The screen's 60 s timeout doesn't know a scan is running yet, which is 2.1's "not now" check.
- 2.4: `WifiAdapter` now runs `check_pdf()` on each upload and rejects the whole batch (nothing left on disk) with the file's name and reason. Email keeps the file-browser check only, as decided. The check runs inside the portal's async route, so a huge or hostile PDF can stall the portal for the seconds it takes to load its pages; moving it to a thread would need the portal's SQLite connection handled first (it is per-thread).
- 2.5: the longer watch showed the existing `media-empty-error` detection does work (after ~30 s), so no detection change was needed. Built on `feature/phase-2`: paper count zeroed on paper-out, one `LOW_PAPER_ALERT_SHEETS` setting, low ink SMSes the operator once per tank and only an admin-entered 0% blocks customers (the estimate stops at 1%), bottle yields in `.env` (still the 17000 placeholder, needs the HP spec sheet), "Refill All" only in SIM_MODE. Not done: the low-ink alert on the dashboard (the `/kiosk` page doesn't exist yet, see 2.6).
