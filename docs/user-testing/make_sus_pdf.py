"""Render the participant-facing SUS page (docs/user-testing/sus-form.pdf).

Run from the repo root:  .venv/bin/python docs/user-testing/make_sus_pdf.py

One A4 page, drawn with PyMuPDF (already a project dependency). The item wording
is the same as sus-form.md; keep the two in step if either changes.
"""
from pathlib import Path

import fitz

OUT = Path(__file__).with_name("sus-form.pdf")

ITEMS = [
    "I think that I would like to use this kiosk frequently.",
    "I found the kiosk unnecessarily complex.",
    "I thought the kiosk was easy to use.",
    "I think that I would need the support of a technical person to be able to use this kiosk.",
    "I found the various functions in this kiosk were well integrated.",
    "I thought there was too much inconsistency in this kiosk.",
    "I would imagine that most people would learn to use this kiosk very quickly.",
    "I found the kiosk very cumbersome to use.",
    "I felt very confident using the kiosk.",
    "I needed to learn a lot of things before I could get going with this kiosk.",
]
SCALE = ["Strongly\nDisagree\n(1)", "Disagree\n(2)", "Neutral\n(3)", "Agree\n(4)", "Strongly\nAgree\n(5)"]

REG, BOLD, ITAL = "tiro", "tibo", "tiit"  # PyMuPDF's built-in Times
BLACK = (0, 0, 0)
GREY = (0.45, 0.45, 0.45)

W, H = fitz.paper_size("a4")
MARGIN = 54
L, R = MARGIN, W - MARGIN


def text(page, rect, s, font=REG, size=11, align=0):
    leftover = page.insert_textbox(fitz.Rect(rect), s, fontname=font, fontsize=size, align=align, color=BLACK)
    if leftover < 0:
        raise SystemExit(f"text does not fit its box ({leftover:.1f}pt short): {s[:40]!r}")


def main():
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    y = 48

    text(page, (L, y, R, y + 32), "Kiosk Usability Survey", BOLD, 18, align=1)
    y += 40

    # Participant details
    text(page, (L, y, L + 108, y + 20), "Participant No.:", BOLD, 11)
    page.draw_line((L + 108, y + 13), (L + 190, y + 13), width=0.6)
    text(page, (L + 215, y, L + 335, y + 20), "Program / Course:", BOLD, 11)
    page.draw_line((L + 335, y + 13), (R, y + 13), width=0.6)
    y += 32

    text(
        page,
        (L, y, R, y + 96),
        "Thank you for trying the kiosk. This survey takes about two minutes. There are no right or "
        "wrong answers: we are testing the kiosk, not you, and your answers are anonymous.\n\n"
        "For each statement, tick the box that best matches how much you agree, based on your "
        "experience with the kiosk just now. If you are unsure, go with your first reaction. "
        "Please answer every statement.",
        REG,
        10.5,
    )
    y += 100

    # Table geometry
    num_w, scale_w = 26, 52
    stmt_w = (R - L) - num_w - 5 * scale_w
    col_x = [L, L + num_w, L + num_w + stmt_w] + [L + num_w + stmt_w + scale_w * i for i in range(1, 6)]
    head_h, row_h = 44, 37

    page.draw_line((L, y), (R, y), width=1)
    text(page, (L, y + 15, col_x[1], y + 35), "#", BOLD, 10, align=1)
    text(page, (col_x[1] + 6, y + 15, col_x[2], y + 35), "Statement", BOLD, 10)
    for i, label in enumerate(SCALE):
        x0 = col_x[2] + scale_w * i
        # Three-line labels start higher than the single-line ones so all sit centred.
        n = label.count("\n") + 1
        top = y + 2 + (3 - n) * 6
        text(page, (x0, top, x0 + scale_w, top + 40), label, BOLD, 8.5, align=1)
    y += head_h
    page.draw_line((L, y), (R, y), width=0.6)

    box = 11
    for n, item in enumerate(ITEMS, 1):
        text(page, (L, y + 10, col_x[1], y + 30), str(n), REG, 10, align=1)
        text(page, (col_x[1] + 6, y + 2, col_x[2] - 6, y + row_h), item, REG, 10)
        for i in range(5):
            cx = col_x[2] + scale_w * i + scale_w / 2
            cy = y + row_h / 2
            page.draw_rect(fitz.Rect(cx - box / 2, cy - box / 2, cx + box / 2, cy + box / 2), width=0.8)
        y += row_h
        page.draw_line((L, y), (R, y), width=0.3 if n < len(ITEMS) else 1)

    # Comments
    y += 22
    text(page, (L, y, R, y + 20), "Comments or feedback (optional):", BOLD, 11)
    y += 18
    for _ in range(4):
        y += 24
        page.draw_line((L, y), (R, y), width=0.4, color=GREY)

    text(page, (L, H - 44, R, H - 24), "Thank you for your time!", ITAL, 10, align=1)

    doc.save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
