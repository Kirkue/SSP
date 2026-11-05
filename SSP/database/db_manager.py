# database/db_manager.py

import json
import sqlite3
import os
from datetime import datetime
from database.voucher_db import VoucherDBMixin

# Canonical Source vocabulary (CONTEXT.md's Source term) — the fixed
# grouping key for the Admin Dashboard's accounting summary.
ACCOUNTING_SOURCES = ("usb", "wifi", "email", "scanner")

# The demo/fixture SQLite file admin_dashboard/seed_demo_data.py populates
# (issue #18) — a completely separate file from the real ssp_database.db,
# read instead of it only when SIM_MODE=true (see
# admin_dashboard/dependencies.py). Already covered by .gitignore's
# `SSP/database/*.db` pattern.
SIM_DB_NAME = "ssp_database.sim.db"


class DatabaseManager(VoucherDBMixin):
    def __init__(self, db_name="ssp_database.db", db_path=None):
        # db_path lets callers (tests, the demo/fixture DB) point at an
        # arbitrary SQLite file instead of the fixed database/ directory
        # below — used e.g. by the admin dashboard's test suite to run
        # against a temp file seeded via models.init_db().
        if db_path is not None:
            self.db_path = db_path
        else:
            # Use the same database file as models.py
            base_dir = os.path.dirname(os.path.dirname(__file__))
            db_dir = os.path.join(base_dir, 'database')
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, db_name)
        self.conn = None
        self.connect()
        # Remove create_tables() call since models.py handles initialization

    def connect(self):
        """Establish a connection to the SQLite database."""
        try:
            # check_same_thread=False: the webapp opens one DatabaseManager
            # per request via a sync FastAPI dependency (see
            # webapp/dependencies.py), and Starlette can resolve that
            # dependency and run the async route body on different
            # threadpool/event-loop threads within the same request. The
            # connection is still only ever touched sequentially within a
            # single request's lifecycle, never concurrently, so this is safe.
            # timeout: wait up to 30 s for another connection's write lock
            # (print completion, the email poller and the webapp each hold
            # their own connection) instead of failing with "database is locked".
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
            self.conn.row_factory = self.dict_factory
            try:
                # WAL lets readers and a writer overlap; the setting persists in the file.
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA busy_timeout=30000")
            except sqlite3.Error as e:
                print(f"⚠️ Could not enable WAL mode: {e}")
            print(f"✅ Database connection established: {self.db_path}")
        except sqlite3.Error as e:
            print(f"❌ Database connection error: {e}")
            self.conn = None

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def dict_factory(self, cursor, row):
        """Convert query results into dictionaries."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    # create_tables() method removed - database initialization is handled by models.py

    # --- NEW: get_setting method ---
    def get_setting(self, key, default=None):
        """Gets a value from the settings table."""
        if not self.conn:
            return default
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            if result:
                # Attempt to convert to int, otherwise return as string
                try:
                    return int(result['value'])
                except (ValueError, TypeError):
                    return result['value']
            return default
        except sqlite3.Error as e:
            print(f"Error getting setting '{key}': {e}")
            return default

    # --- NEW: update_setting method ---
    def update_setting(self, key, value):
        """Updates or inserts a value in the settings table."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            # Use INSERT OR REPLACE to handle both new and existing keys
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating setting '{key}': {e}")

    # --- Existing Methods (assuming they are here) ---
    def log_transaction(self, data):
        """Insert a transactions row. Returns True if it was written (False
        if there is no connection, the row failed, or its payment_ref is
        already logged)."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (timestamp, file_name, pages, copies, color_mode, total_cost,
                    amount_paid, change_given, status, error_message, source,
                    change_dispensed, voucher_issued, voucher_applied, payment_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(), data['file_name'], data['pages'], data['copies'], data['color_mode'],
                data['total_cost'], data['amount_paid'], data['change_given'], data['status'],
                data.get('error_message', None), data.get('source', None),
                data.get('change_dispensed', None), data.get('voucher_issued', 0),
                data.get('voucher_applied', 0), data.get('payment_ref', None)
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error logging transaction: {e}")
            return False

    def get_transaction_by_ref(self, payment_ref):
        if not self.conn or not payment_ref:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions WHERE payment_ref = ?", (payment_ref,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error reading transaction {payment_ref}: {e}")
            return None

    def update_transaction_outcome(self, payment_ref, status, from_status=None,
                                   voucher_issued=None, error_message=None):
        """Record a settled transaction's print outcome, found by payment_ref.
        With `from_status`, only a row still in that status changes, so an
        outcome is applied at most once. Returns True if a row changed."""
        if not self.conn or not payment_ref:
            return False
        try:
            sets, params = ["status = ?"], [status]
            if voucher_issued is not None:
                sets.append("voucher_issued = ?")
                params.append(voucher_issued)
            if error_message is not None:
                sets.append("error_message = ?")
                params.append(error_message)
            query = f"UPDATE transactions SET {', '.join(sets)} WHERE payment_ref = ?"
            params.append(payment_ref)
            if from_status is not None:
                query += " AND status = ?"
                params.append(from_status)
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            print(f"Error updating transaction {payment_ref}: {e}")
            return False

    def adjust_cash_inventory(self, denomination, delta, type):
        """Add `delta` (may be negative) to a stock count, never below 0."""
        current = 0
        for item in self.get_cash_inventory():
            if item.get('denomination') == denomination and item.get('type') == type:
                current = item.get('count', 0)
                break
        self.update_cash_inventory(denomination=denomination, count=max(0, current + delta), type=type)

    def get_transaction_history(self):
        if not self.conn:
            print("❌ ERROR: No database connection for get_transaction_history")
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM transactions ORDER BY timestamp DESC")
            results = cursor.fetchall()
            print(f"✅ Retrieved {len(results)} transactions from database")
            return results
        except sqlite3.Error as e:
            print(f"❌ ERROR: Failed to get transaction history: {e}")
            return []
        except Exception as e:
            print(f"❌ ERROR: Unexpected error in get_transaction_history: {e}")
            return []

    def update_cash_inventory(self, denomination, count, type):
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT count FROM cash_inventory WHERE denomination = ? AND type = ?", (denomination, type))
            result = cursor.fetchone()
            if result:
                # Set the count to the new value (not add to existing)
                cursor.execute(
                    "UPDATE cash_inventory SET count = ?, last_updated = ? WHERE denomination = ? AND type = ?",
                    (count, datetime.now(), denomination, type)
                )
            else:
                cursor.execute(
                    "INSERT INTO cash_inventory (denomination, count, type, last_updated) VALUES (?, ?, ?, ?)",
                    (denomination, count, type, datetime.now())
                )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating cash inventory: {e}")

    def get_cash_inventory(self):
        if not self.conn:
            print("❌ ERROR: No database connection for get_cash_inventory")
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM cash_inventory ORDER BY denomination ASC")
            results = cursor.fetchall()
            print(f"✅ Retrieved {len(results)} cash inventory items from database")
            return results
        except sqlite3.Error as e:
            print(f"❌ ERROR: Failed to get cash inventory: {e}")
            return []
        except Exception as e:
            print(f"❌ ERROR: Unexpected error in get_cash_inventory: {e}")
            return []

    def log_error(self, error_type, message, context):
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO error_log (timestamp, error_type, error_message, screen_name, resolved) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(), error_type, message, context, False)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error logging error: {e}")

    def get_error_log(self):
        if not self.conn:
            print("❌ ERROR: No database connection for get_error_log")
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM error_log ORDER BY timestamp DESC")
            results = cursor.fetchall()
            print(f"✅ Retrieved {len(results)} error log entries from database")
            return results
        except sqlite3.Error as e:
            print(f"❌ ERROR: Failed to get error log: {e}")
            return []
        except Exception as e:
            print(f"❌ ERROR: Unexpected error in get_error_log: {e}")
            return []

    # --- NEW: get_supplies_status method ---
    def get_supplies_status(self):
        """Get current paper and coin inventory status."""
        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor()

            # Get paper count from settings
            cursor.execute("SELECT value FROM settings WHERE key = 'paper_count'")
            paper_result = cursor.fetchone()
            paper_count = int(paper_result['value']) if paper_result else 0

            # Get coin inventory
            cursor.execute("""
                SELECT denomination, count
                FROM cash_inventory
                WHERE type = 'coin' AND denomination IN (1.0, 5.0)
            """)
            coins = {row['denomination']: row['count'] for row in cursor.fetchall()}

            # Build status dictionary
            status = {
                "paper_count": paper_count,
                "coins": {
                    "peso_1": coins.get(1.0, 0),
                    "peso_5": coins.get(5.0, 0)
                },
                "warnings": []
            }

            # Add warnings based on thresholds
            if paper_count < 20:
                status["warnings"].append("Low paper level!")
            if coins.get(1.0, 0) < 50:
                status["warnings"].append("Low on ₱1 coins!")
            if coins.get(5.0, 0) < 20:
                status["warnings"].append("Low on ₱5 coins!")

            return status

        except sqlite3.Error as e:
            print(f"Error getting supplies status: {e}")
            return None

    def update_paper_count(self, count):
        """Update the paper count in settings."""
        self.update_setting('paper_count', count)

    # --- NEW: CMYK Ink Level Methods ---
    def get_cmyk_ink_levels(self):
        """Get the current CMYK ink levels."""
        import threading
        current_thread = threading.current_thread()
        print(f"DEBUG: get_cmyk_ink_levels called from thread: {current_thread.name} (id: {current_thread.ident})")
        print(f"DEBUG: Database connection: {self.conn}")

        if not self.conn:
            print("DEBUG: No database connection available")
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT cyan_level, magenta_level, yellow_level, black_level, last_updated
                FROM cmyk_ink_levels
                ORDER BY last_updated DESC
                LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                try:
                    return {
                        'cyan': float(result['cyan_level']),
                        'magenta': float(result['magenta_level']),
                        'yellow': float(result['yellow_level']),
                        'black': float(result['black_level']),
                        'last_updated': result['last_updated']
                    }
                except (ValueError, TypeError) as e:
                    print(f"Error converting CMYK values from database: {e}")
                    print(f"Raw values: cyan={result['cyan_level']}, magenta={result['magenta_level']}, "
                          f"yellow={result['yellow_level']}, black={result['black_level']}")
                    # Return default values if conversion fails
                    return {
                        'cyan': 100.0,
                        'magenta': 100.0,
                        'yellow': 100.0,
                        'black': 100.0,
                        'last_updated': result['last_updated']
                    }
            return None
        except sqlite3.Error as e:
            print(f"Error getting CMYK ink levels: {e}")
            return None

    def update_cmyk_ink_levels(self, cyan, magenta, yellow, black):
        """Update CMYK ink levels with decimal precision."""
        if not self.conn:
            return False
        try:
            # Ensure values are properly converted to float
            cyan_float = float(cyan)
            magenta_float = float(magenta)
            yellow_float = float(yellow)
            black_float = float(black)

            print(f"DEBUG: Storing CMYK values as floats: C:{cyan_float}, M:{magenta_float}, Y:{yellow_float}, K:{black_float}")

            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO cmyk_ink_levels (cyan_level, magenta_level, yellow_level, black_level, timestamp, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cyan_float, magenta_float, yellow_float, black_float, datetime.now(), datetime.now()))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error updating CMYK ink levels: {e}")
            return False
        except ValueError as e:
            print(f"Error converting CMYK values to float: {e}")
            return False

    def get_cmyk_ink_history(self, limit=10):
        """Get CMYK ink level history."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT cyan_level, magenta_level, yellow_level, black_level, last_updated
                FROM cmyk_ink_levels
                ORDER BY last_updated DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting CMYK ink history: {e}")
            return []

    # --- NEW: Session methods (OTP + QR intake sessions) ---
    def create_session(
        self, session_id, otp_hash, source, files,
        created_at, expires_at, metadata=None
    ):
        """Insert a new intake session. `files` is a list of
        {"path": ..., "original_filename": ...} dicts, JSON-encoded for
        storage. Returns True on success."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO sessions
                    (session_id, otp_hash, source, files,
                     status, failed_attempts, created_at, expires_at, metadata)
                VALUES (?, ?, ?, ?, 'pending', 0, ?, ?, ?)
            """, (session_id, otp_hash, source, json.dumps(files),
                  created_at, expires_at, metadata))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error creating session: {e}")
            return False

    def get_session(self, session_id):
        """Fetch a session row by its public session_id, or None."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error getting session '{session_id}': {e}")
            return None

    def get_verifiable_sessions(self, source):
        """Sessions for `source` not yet in a terminal state, for OTP
        resolution when no session_id is known (manual kiosk entry)."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE source = ? AND status IN ('pending', 'locked') "
                "ORDER BY created_at DESC", (source,)
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting verifiable sessions for source '{source}': {e}")
            return []

    def increment_session_failed_attempts(self, session_id):
        """Increment failed_attempts for a session and return the new count."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE sessions SET failed_attempts = failed_attempts + 1 WHERE session_id = ?",
                (session_id,)
            )
            self.conn.commit()
            cursor.execute("SELECT failed_attempts FROM sessions WHERE session_id = ?", (session_id,))
            result = cursor.fetchone()
            return result['failed_attempts'] if result else None
        except sqlite3.Error as e:
            print(f"Error incrementing failed attempts for session '{session_id}': {e}")
            return None

    def set_session_status(self, session_id, status):
        """Update a session's status ('pending', 'verified', 'expired', 'locked')."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status, session_id)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error setting status for session '{session_id}': {e}")

    def get_expired_sessions(self, now):
        """Return sessions whose expires_at has passed and aren't already marked expired."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM sessions WHERE expires_at <= ? AND status != 'expired'",
                (now,)
            )
            return cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error getting expired sessions: {e}")
            return []

    def delete_session(self, session_id):
        """Remove a session row (called after its temp directory has been cleaned up)."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error deleting session '{session_id}': {e}")

    # --- NEW: Email intake log methods ---
    def get_email_intake_log(self, uidvalidity, uid):
        """Fetch a logged intake outcome for a (uidvalidity, uid) pair, or None."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM email_intake_log WHERE uidvalidity = ? AND uid = ?",
                (uidvalidity, uid)
            )
            return cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error getting email intake log for uid {uid}: {e}")
            return None

    def log_email_intake(self, uidvalidity, uid, message_id, outcome, session_id):
        """
        Record an email intake outcome. Uses INSERT OR IGNORE against the
        UNIQUE(uidvalidity, uid) constraint so a re-poll racing on the same
        uid just no-ops instead of double-logging. Returns True if this call
        actually inserted the row (i.e. the caller should act on the result,
        such as marking the message Seen), False if it was already logged.
        """
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO email_intake_log
                    (uidvalidity, uid, message_id, outcome, session_id, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uidvalidity, uid, message_id, outcome, session_id, datetime.now()))
            self.conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as e:
            print(f"Error logging email intake for uid {uid}: {e}")
            return False

    # --- NEW: Admin Dashboard user account methods (see admin_dashboard/) ---
    def get_user_by_username(self, username):
        """Fetch a dashboard account row by username, or None."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            return cursor.fetchone()
        except sqlite3.Error as e:
            print(f"Error getting user '{username}': {e}")
            return None

    def create_user(self, username, password_hash, role):
        """Insert a new dashboard account. `password_hash` must already be
        hashed (Argon2id) by the caller — never store a plaintext password.
        Returns True on success, False if the username is already taken."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, role, datetime.now())
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.Error as e:
            print(f"Error creating user '{username}': {e}")
            return False

    def update_user_password(self, username, password_hash):
        """Reset an existing account's password hash. Returns True if a
        matching account was found and updated, False otherwise."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username)
            )
            self.conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as e:
            print(f"Error updating password for '{username}': {e}")
            return False

    # --- NEW: Admin Dashboard lockout + login audit log (issue #14) ---
    def increment_failed_login_attempts(self, username):
        """Increment a user's consecutive-failed-attempt counter. Returns the
        new count, or None if the user doesn't exist / on error."""
        if not self.conn:
            return None
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE username = ?",
                (username,)
            )
            self.conn.commit()
            cursor.execute("SELECT failed_attempts FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return row["failed_attempts"] if row else None
        except sqlite3.Error as e:
            print(f"Error incrementing failed attempts for '{username}': {e}")
            return None

    def set_account_lock(self, username, locked_until):
        """Lock `username` out of login until `locked_until`."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET locked_until = ? WHERE username = ?",
                (locked_until, username)
            )
            self.conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as e:
            print(f"Error locking account '{username}': {e}")
            return False

    def reset_failed_login_attempts(self, username):
        """Clear a user's failed-attempt counter and any active lock —
        called after a successful login."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
                (username,)
            )
            self.conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error as e:
            print(f"Error resetting failed attempts for '{username}': {e}")
            return False

    def record_login_attempt(self, username, success, source_ip):
        """Append a row to the dashboard login audit log. Called for every
        login attempt, successful or not, including unknown usernames."""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO dashboard_login_log (timestamp, username, success, source_ip) "
                "VALUES (?, ?, ?, ?)",
                (datetime.now(), username, success, source_ip)
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Error recording login attempt for '{username}': {e}")
            return False

    def get_login_log(self, username=None):
        """Return dashboard login audit log rows in insertion order,
        optionally filtered by username."""
        if not self.conn:
            return []
        cursor = self.conn.cursor()
        if username is not None:
            cursor.execute("SELECT * FROM dashboard_login_log WHERE username = ? ORDER BY id", (username,))
        else:
            cursor.execute("SELECT * FROM dashboard_login_log ORDER BY id")
        return cursor.fetchall()

    # --- NEW: Admin Dashboard accounting aggregates (issue #15) ---
    def get_accounting_summary(self, since=None):
        """Per-Source revenue (sum of total_cost) and transaction count for
        completed transactions, optionally scoped to timestamp >= `since`.
        Always returns one row per canonical Source (see CONTEXT.md's
        Source term), zero-filled for a source with no matching rows in
        the window, in a fixed order — so the accounting page's table
        shape never depends on which sources happen to have data.

        A `scanner`-sourced row is counted the same as any other: it is a
        Photocopy, a paid Digital Copy (copies = 0) or both (see CONTEXT.md)."""
        if not self.conn:
            return []
        try:
            cursor = self.conn.cursor()
            query = (
                "SELECT source, COALESCE(SUM(total_cost), 0) AS revenue, COUNT(*) AS transaction_count "
                "FROM transactions WHERE status = 'completed' AND source IS NOT NULL"
            )
            params = []
            if since is not None:
                query += " AND timestamp >= ?"
                params.append(since)
            query += " GROUP BY source"
            cursor.execute(query, params)
            by_source = {row["source"]: row for row in cursor.fetchall()}
            empty = {"revenue": 0, "transaction_count": 0}
            return [
                {"source": source, **by_source.get(source, empty)}
                for source in ACCOUNTING_SOURCES
            ]
        except sqlite3.Error as e:
            print(f"Error getting accounting summary: {e}")
            return []

    def get_change_and_voucher_totals(self, since=None):
        """Change actually dispensed, Voucher value issued and Voucher value
        Applied (issue #28), summed over the same completed transactions as
        get_accounting_summary; Voucher value issued also counts abandoned
        payments (cancelled_partial_payment), whose cash became a Voucher.
        Optionally scoped to timestamp >= `since`. Rows logged before #23 have
        a NULL change_dispensed and count as 0."""
        empty = {"change_dispensed": 0, "voucher_issued": 0, "voucher_applied": 0}
        if not self.conn:
            return empty
        try:
            cursor = self.conn.cursor()
            query = (
                "SELECT COALESCE(SUM(CASE WHEN status IN ('completed', 'print_failed', 'digital_failed') "
                "THEN change_dispensed END), 0) AS change_dispensed, "
                "COALESCE(SUM(voucher_issued), 0) AS voucher_issued, "
                "COALESCE(SUM(CASE WHEN status IN ('completed', 'print_failed', 'digital_failed') "
                "THEN voucher_applied END), 0) AS voucher_applied "
                "FROM transactions WHERE status IN "
                "('completed', 'print_failed', 'digital_failed', 'cancelled_partial_payment')"
            )
            params = []
            if since is not None:
                query += " AND timestamp >= ?"
                params.append(since)
            cursor.execute(query, params)
            return dict(cursor.fetchone())
        except sqlite3.Error as e:
            print(f"Error getting change and voucher totals: {e}")
            return empty

    def get_supplies_status_with_cmyk(self):
        """Get current supplies status including CMYK ink levels."""
        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor()

            # Get paper count from settings
            cursor.execute("SELECT value FROM settings WHERE key = 'paper_count'")
            paper_result = cursor.fetchone()
            paper_count = int(paper_result['value']) if paper_result else 0

            # Get coin inventory
            cursor.execute("""
                SELECT denomination, count
                FROM cash_inventory
                WHERE type = 'coin' AND denomination IN (1, 5)
            """)
            coins = {row['denomination']: row['count'] for row in cursor.fetchall()}

            # Get CMYK ink levels
            cmyk_levels = self.get_cmyk_ink_levels()

            # Build status dictionary
            status = {
                "paper_count": paper_count,
                "coins": {
                    "peso_1": coins.get(1.0, 0),
                    "peso_5": coins.get(5.0, 0)
                },
                "cmyk_levels": cmyk_levels,
                "warnings": []
            }

            # Add warnings based on thresholds
            if paper_count < 20:
                status["warnings"].append("Low paper level!")
            if coins.get(1.0, 0) < 50:
                status["warnings"].append("Low on ₱1 coins!")
            if coins.get(5.0, 0) < 20:
                status["warnings"].append("Low on ₱5 coins!")

            # Add CMYK ink warnings
            if cmyk_levels:
                if cmyk_levels['cyan'] < 10.0:
                    status["warnings"].append("Low Cyan ink level!")
                if cmyk_levels['magenta'] < 10.0:
                    status["warnings"].append("Low Magenta ink level!")
                if cmyk_levels['yellow'] < 10.0:
                    status["warnings"].append("Low Yellow ink level!")
                if cmyk_levels['black'] < 10.0:
                    status["warnings"].append("Low Black ink level!")

            return status

        except sqlite3.Error as e:
            print(f"Error getting supplies status with CMYK: {e}")
            return None
