"""
WhatsApp contact registry.

Maps an inbound WhatsApp phone number to a stable (user_id, session_id) pair
so every message from the same number lands in the same ADK session.

Also stores:
  - ai_muted   : when True, the agent is silenced and the agent replies manually
  - display_name : pulled from Meta's contact profile (optional)

Table lives in the existing bookings.db — zero new infrastructure.
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bookings.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_contacts (
                phone        TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                session_id   TEXT NOT NULL,
                display_name TEXT,
                ai_muted     INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                phone        TEXT NOT NULL,
                direction    TEXT NOT NULL,   -- 'inbound' | 'outbound'
                sender_label TEXT,            -- display name or 'Agent'
                text         TEXT NOT NULL,   -- full raw text (including card markers for UI)
                wa_message_id TEXT,           -- Meta's message ID (for dedup)
                created_at   TEXT NOT NULL
            )
        """)
        # Index for fast per-phone lookups
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_wa_messages_phone
            ON whatsapp_messages (phone, created_at DESC)
        """)


_init()


def get_or_create_contact(phone: str, display_name: Optional[str] = None) -> dict:
    """
    Return the contact record for *phone*, creating one if it doesn't exist yet.
    user_id  = "wa_{phone}"   (e.g. "wa_+919876543210")
    session_id = "wa_session_{phone}" — one persistent session per WhatsApp number.
    """
    phone = phone.strip()
    now = datetime.now(timezone.utc).isoformat()

    with _conn() as c:
        row = c.execute(
            "SELECT * FROM whatsapp_contacts WHERE phone = ?", (phone,)
        ).fetchone()

        if row:
            # Optionally update display_name if we now have one
            if display_name and not row["display_name"]:
                c.execute(
                    "UPDATE whatsapp_contacts SET display_name=?, updated_at=? WHERE phone=?",
                    (display_name, now, phone),
                )
                return {**dict(row), "display_name": display_name}
            return dict(row)

        # New contact — create stable identities
        user_id = f"wa_{phone}"
        session_id = f"wa_session_{phone}"
        c.execute("""
            INSERT INTO whatsapp_contacts
                (phone, user_id, session_id, display_name, ai_muted, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
        """, (phone, user_id, session_id, display_name, now, now))

    return {
        "phone": phone,
        "user_id": user_id,
        "session_id": session_id,
        "display_name": display_name,
        "ai_muted": 0,
        "created_at": now,
        "updated_at": now,
    }


def get_contact(phone: str) -> Optional[dict]:
    """Return existing contact or None."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM whatsapp_contacts WHERE phone = ?", (phone.strip(),)
        ).fetchone()
    return dict(row) if row else None


def set_ai_muted(phone: str, muted: bool) -> bool:
    """Toggle AI mute for a contact. Returns False if contact not found."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        cur = c.execute(
            "UPDATE whatsapp_contacts SET ai_muted=?, updated_at=? WHERE phone=?",
            (1 if muted else 0, now, phone.strip()),
        )
        return cur.rowcount > 0


def list_contacts() -> list[dict]:
    """Return all WhatsApp contacts, newest first."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM whatsapp_contacts ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Message log ───────────────────────────────────────────────────────────────

def save_message(
    phone: str,
    direction: str,          # 'inbound' | 'outbound'
    text: str,
    sender_label: Optional[str] = None,
    wa_message_id: Optional[str] = None,
) -> dict:
    """Persist a WhatsApp message (inbound from user, or outbound from agent/human)."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        cur = c.execute("""
            INSERT INTO whatsapp_messages
                (phone, direction, sender_label, text, wa_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (phone.strip(), direction, sender_label, text, wa_message_id, now))
        row_id = cur.lastrowid

    return {
        "id": row_id,
        "phone": phone,
        "direction": direction,
        "sender_label": sender_label,
        "text": text,
        "wa_message_id": wa_message_id,
        "created_at": now,
    }


def get_messages_for_phone(phone: str, limit: int = 100) -> list[dict]:
    """Return the most recent messages for a phone number, oldest first."""
    with _conn() as c:
        rows = c.execute("""
            SELECT * FROM whatsapp_messages
            WHERE phone = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (phone.strip(), limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def message_already_processed(wa_message_id: str) -> bool:
    """True if we've already handled this Meta message ID (idempotency guard)."""
    if not wa_message_id:
        return False
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM whatsapp_messages WHERE wa_message_id = ?",
            (wa_message_id,),
        ).fetchone()
    return row is not None
