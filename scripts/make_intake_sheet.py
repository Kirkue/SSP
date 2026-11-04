"""
Writes a one-page printable PDF telling first-time customers how to send a file
to the kiosk by Wi-Fi or email, with QR codes, for taping to the machine.

The addresses come from .env through the same functions the Wi-Fi and email
screens use, so the sheet matches what the kiosk shows. Run it on the kiosk
with the kiosk's venv Python, from the repo root (where .env lives):

    python scripts/make_intake_sheet.py            # writes intake_sheet.pdf
    python scripts/make_intake_sheet.py --print    # also sends it to the printer (lp)
"""
import argparse
import io
import os
import subprocess
import sys
from urllib.parse import quote

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "SSP"))

import fitz  # noqa: E402
import qrcode  # noqa: E402

from config import get_config  # noqa: E402
from managers.webapp_thread import wifi_portal_url  # noqa: E402

PAGE_W, PAGE_H = fitz.paper_size("a4")
MARGIN = 44
QR_SIZE = 118
DARK = (0.1, 0.1, 0.1)
GREY = (0.35, 0.35, 0.35)


def wifi_join_payload(ssid):
    """QR payload that joins an open Wi-Fi network (the hotspot has no password, ADR 0007)."""
    escaped = "".join("\\" + ch if ch in '\\;,:"' else ch for ch in ssid)
    return f"WIFI:T:nopass;S:{escaped};;"


def _qr_png(data):
    buf = io.BytesIO()
    qrcode.make(data, border=1).save(buf, format="PNG")
    return buf.getvalue()


class Sheet:
    def __init__(self):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN

    def text(self, s, size=12, bold=False, color=DARK, x=MARGIN, width=None, gap=6):
        width = width or PAGE_W - x - MARGIN
        font = "hebo" if bold else "helv"
        rect = fitz.Rect(x, self.y, x + width, self.y + 400)
        left = self.page.insert_textbox(rect, s, fontsize=size, fontname=font, color=color)
        used = 400 - left  # insert_textbox returns the unused height
        self.y += used + gap
        return used

    def step(self, number, title, detail, qr_data=None, qr_caption=None, highlight=None):
        """One numbered step: text on the left, an optional QR on the right.
        `highlight` (an address to type) is shown large and dark under the title."""
        top = self.y
        text_w = PAGE_W - 2 * MARGIN - (QR_SIZE + 20 if qr_data else 0)
        self.text(f"{number}. {title}", size=14, bold=True, width=text_w, gap=4)
        if highlight:
            self.text(highlight, size=13, bold=True, x=MARGIN + 18, width=text_w - 18, gap=4)
        self.text(detail, size=11, color=GREY, x=MARGIN + 18, width=text_w - 18)
        bottom = self.y
        if qr_data:
            x = PAGE_W - MARGIN - QR_SIZE
            self.page.insert_image(fitz.Rect(x, top, x + QR_SIZE, top + QR_SIZE),
                                   stream=_qr_png(qr_data))
            bottom = max(bottom, top + QR_SIZE)
            if qr_caption:
                cap = fitz.Rect(x - 10, bottom + 2, x + QR_SIZE + 10, bottom + 30)
                self.page.insert_textbox(cap, qr_caption, fontsize=9, fontname="helv",
                                         color=GREY, align=fitz.TEXT_ALIGN_CENTER)
                bottom += 18
        self.y = bottom + 10

    def rule(self):
        self.page.draw_line((MARGIN, self.y), (PAGE_W - MARGIN, self.y), color=(0.75, 0.75, 0.75), width=1)
        self.y += 14


def build(path):
    config = get_config()
    portal = wifi_portal_url()
    hotspot = config.wifi_hotspot_enabled and not config.sim_mode
    address = config.email_user
    keyword = config.email_subject_keyword

    sheet = Sheet()
    sheet.text("Print from your phone", size=24, bold=True, gap=4)
    sheet.text("Send your PDF to this kiosk by Wi-Fi or email, then type the 6-digit code "
               "you get on the kiosk's screen (or hold its QR code up to the reader).",
               size=12, color=GREY, gap=14)

    sheet.text("By Wi-Fi", size=18, bold=True, gap=10)
    n = 1
    if hotspot:
        sheet.step(n, f'Join the Wi-Fi network "{config.wifi_hotspot_ssid}"',
                   "No password needed. Scan the code with your camera, or pick it in Wi-Fi settings. "
                   "It has no internet; stay connected anyway.",
                   wifi_join_payload(config.wifi_hotspot_ssid), "Join Wi-Fi")
    else:
        sheet.step(n, "Connect to the same network as this kiosk", "Ask staff which network to use.")
    n += 1
    sheet.step(n, "Open the upload page",
               'If your browser says the connection is "not private", tap Advanced, then Proceed. '
               "Page won't load? Turn off any VPN on your phone.",
               portal, "Open upload page", highlight=portal)
    n += 1
    sheet.step(n, "Upload your PDF and get your code",
               "On the kiosk, choose Wi-Fi, then type the 6-digit code shown on your phone.")

    sheet.rule()
    sheet.text("By email", size=18, bold=True, gap=10)
    if address:
        sheet.step(1, "Email your PDF as an attachment",
                   "Scanning the code opens a new email with both filled in; attach your PDF and send.",
                   f"mailto:{address}?subject={quote(keyword)}", "New email",
                   highlight=f"To: {address}\nSubject must contain: {keyword}")
        sheet.step(2, "Get your code by reply",
                   "Within a minute you'll get a reply with a 6-digit code. On the kiosk, choose Email "
                   "and type it.")
    else:
        sheet.text("(Email isn't set up on this kiosk: EMAIL_USER is blank in .env.)", color=GREY)

    sheet.doc.save(path)
    sheet.doc.close()
    print(f"Wrote {path}")
    print(f"  Wi-Fi: {config.wifi_hotspot_ssid if hotspot else '(no hotspot)'}  ->  {portal}")
    print(f"  Email: {address or '(not configured)'}  subject: {keyword}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("output", nargs="?", default="intake_sheet.pdf")
    parser.add_argument("--print", action="store_true", help="send the PDF to the default printer with lp")
    args = parser.parse_args(argv)

    build(args.output)
    if args.print:
        subprocess.run(["lp", args.output], check=True)


if __name__ == "__main__":
    main()
