# admin_dashboard/seed_demo_data.py
#
# Seeds the SIM_MODE-gated demo fixture file (database.db_manager.SIM_DB_NAME,
# i.e. SSP/database/ssp_database.sim.db) with realistic transactions spanning
# all four Source values and a wide enough time spread that /accounting's
# Today/Week/Month/All Time filters each show different, sensible totals
# (issue #18) — so the accounting page can be visually checked before the
# kiosk has accumulated any real transaction history.
#
# Never touches the real ssp_database.db: it only ever opens SIM_DB_PATH,
# a distinct file (already covered by .gitignore's `SSP/database/*.db`).
# Refuses to run unless SIM_MODE=true, so it can't be run by accident
# against a real-hardware checkout.
#
# Usage (from the repo root):
#   make seed-demo-data
#   # or directly:
#   SIM_MODE=true PYTHONPATH=SSP python -m admin_dashboard.seed_demo_data

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import get_config
from database.db_manager import SIM_DB_NAME
from database.models import init_db

SIM_DB_PATH = Path(__file__).resolve().parent.parent / "database" / SIM_DB_NAME

# (source, total_cost, age) fixtures. `age` is how long ago each transaction
# happened, relative to when the script runs — grouped so every time filter
# lands on a different, non-empty slice: "today" (hours old), "this week but
# not today", "this month but not this week", and "older than a month" (only
# All Time includes these). All four Source values appear in every bucket.
FIXTURES = [
    # today
    ("usb", 15.0, timedelta(hours=1)),
    ("wifi", 8.0, timedelta(hours=3)),
    ("email", 12.5, timedelta(hours=5)),
    ("scanner", 5.0, timedelta(hours=6)),
    # this week, not today
    ("usb", 20.0, timedelta(days=2)),
    ("wifi", 10.0, timedelta(days=3)),
    ("email", 7.5, timedelta(days=4)),
    ("scanner", 6.0, timedelta(days=5)),
    # this month, not this week
    ("usb", 30.0, timedelta(days=10)),
    ("wifi", 18.0, timedelta(days=15)),
    ("email", 9.0, timedelta(days=20)),
    ("scanner", 4.0, timedelta(days=25)),
    # older than a month — All Time only
    ("usb", 50.0, timedelta(days=45)),
    ("wifi", 22.0, timedelta(days=60)),
    ("email", 11.0, timedelta(days=90)),
    ("scanner", 8.0, timedelta(days=120)),
]


def seed_transaction(conn, source, total_cost, status="completed", timestamp=None):
    """Raw insert against the real `transactions` schema, bypassing
    DatabaseManager.log_transaction — this script targets the separate
    SIM_MODE-gated demo DB (`SIM_DB_PATH`), never the real `ssp_database.db`
    that log_transaction writes to, so going through the real kiosk print
    flow isn't an option here regardless of what log_transaction does.
    Shared by this script's fixture data and
    tests/test_admin_dashboard.py's transaction-seeding tests, so the one
    raw-SQL shape only needs to be kept in sync with the schema in one
    place."""
    conn.execute(
        "INSERT INTO transactions "
        "(timestamp, file_name, pages, copies, color_mode, total_cost, amount_paid, change_given, status, source) "
        "VALUES (?, 'demo.pdf', 1, 1, 'Color', ?, ?, 0, ?, ?)",
        (timestamp or datetime.now(), total_cost, total_cost, status, source),
    )


def seed(db_path=None):
    """Create (if needed) and populate the demo DB at `db_path` (default:
    SIM_DB_PATH). Returns the path seeded. Callers (e.g. tests) can pass a
    temp path to exercise this without touching the real fixture file."""
    target = str(db_path) if db_path is not None else str(SIM_DB_PATH)
    init_db(db_path=target)

    conn = sqlite3.connect(target)
    try:
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for source, total_cost, age in FIXTURES:
            timestamp = now - age
            if age < timedelta(days=1):
                # "Today" rows are hours old; shortly after midnight that would
                # land on yesterday, so keep them inside today's window.
                timestamp = max(timestamp, midnight)
            seed_transaction(conn, source, total_cost, timestamp=timestamp)
        conn.commit()
    finally:
        conn.close()
    return target


def main():
    config = get_config()
    if not config.sim_mode:
        print(
            "Refusing to seed demo data: SIM_MODE is not enabled. "
            "Set SIM_MODE=true (see .env.example) before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)

    target = seed()
    print(f"OK - seeded demo data into {target}")


if __name__ == "__main__":
    main()
