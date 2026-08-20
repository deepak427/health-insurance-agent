"""
Booking store — SQLite table mapping reference numbers to booking details.
Uses the same DB file as ADK sessions for zero extra infrastructure.
"""
import json
import random
import sqlite3
import string
import os
from datetime import datetime, timezone
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bookings.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                ref_number   TEXT PRIMARY KEY,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                session_id   TEXT NOT NULL,
                policy_name  TEXT NOT NULL,
                insurer      TEXT,
                destination  TEXT,
                travel_dates TEXT,
                num_adults   INTEGER,
                num_children INTEGER,
                traveller_ages TEXT,
                sum_insured  TEXT,
                premium      TEXT,
                artifact_ids TEXT,   -- JSON array of artifact filenames
                addons       TEXT,   -- JSON array of selected addon keys
                status       TEXT DEFAULT 'confirmed',
                notes        TEXT
            )
        """)
        # Migrate: add addons column if it doesn't exist (existing installs)
        try:
            c.execute("ALTER TABLE bookings ADD COLUMN addons TEXT")
        except Exception:
            pass  # column already exists


_init()


def _gen_ref() -> str:
    """Generate a human-readable reference like BUD-A3F7K."""
    chars = string.ascii_uppercase + string.digits
    return "BUD-" + "".join(random.choices(chars, k=5))


def create_booking(
    user_id: str,
    session_id: str,
    policy_name: str,
    insurer: str = "",
    destination: str = "",
    travel_dates: str = "",
    num_adults: int = 0,
    num_children: int = 0,
    traveller_ages: str = "",
    sum_insured: str = "",
    premium: str = "",
    artifact_ids: Optional[list] = None,
    addons: Optional[list] = None,
    notes: str = "",
    status: str = "pending_docs",
) -> str:
    """Create a booking record and return the reference number."""
    now = datetime.now(timezone.utc).isoformat()
    # Ensure unique ref
    while True:
        ref = _gen_ref()
        with _conn() as c:
            exists = c.execute("SELECT 1 FROM bookings WHERE ref_number=?", (ref,)).fetchone()
            if not exists:
                break

    with _conn() as c:
        c.execute("""
            INSERT INTO bookings (
                ref_number, created_at, updated_at, user_id, session_id,
                policy_name, insurer, destination, travel_dates,
                num_adults, num_children, traveller_ages,
                sum_insured, premium, artifact_ids, addons, status, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ref, now, now, user_id, session_id,
            policy_name, insurer, destination, travel_dates,
            num_adults, num_children, traveller_ages,
            sum_insured, premium,
            json.dumps(artifact_ids or []),
            json.dumps(addons or []),
            status or "pending_docs", notes,
        ))
    return ref


def get_booking(ref_number: str) -> Optional[dict]:
    """Fetch a booking by reference number. Returns None if not found."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM bookings WHERE ref_number=?", (ref_number.upper().strip(),)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["artifact_ids"] = json.loads(d.get("artifact_ids") or "[]")
    d["addons"] = json.loads(d.get("addons") or "[]")
    return d


def get_recent_bookings(user_id: str, limit: int = 5) -> list:
    """Return the most recent bookings for a user, newest first."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM bookings WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["artifact_ids"] = json.loads(d.get("artifact_ids") or "[]")
        d["addons"] = json.loads(d.get("addons") or "[]")
        result.append(d)
    return result


def update_booking(ref_number: str, **fields) -> bool:
    """Update allowed fields on a booking. Returns True if found and updated."""
    allowed = {
        "status", "notes", "artifact_ids", "travel_dates",
        "num_adults", "num_children", "traveller_ages",
        "sum_insured", "premium", "destination", "addons",
        "policy_name", "insurer",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "artifact_ids" in updates and isinstance(updates["artifact_ids"], list):
        updates["artifact_ids"] = json.dumps(updates["artifact_ids"])
    if "addons" in updates and isinstance(updates["addons"], list):
        updates["addons"] = json.dumps(updates["addons"])
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [ref_number.upper().strip()]
    with _conn() as c:
        cur = c.execute(
            f"UPDATE bookings SET {set_clause} WHERE ref_number=?", values
        )
        return cur.rowcount > 0
