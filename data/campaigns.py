"""
Campaigns database operations — manages admin broadcast campaigns, audience filtering,
scheduling, and delivery to insurance agents/users.
"""
import sqlite3
import os
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bookings.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_campaigns_db():
    """Create campaigns and campaign_messages tables if they don't exist."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                message         TEXT NOT NULL,
                filter_type     TEXT NOT NULL DEFAULT 'all',
                filter_value    REAL DEFAULT 0.0,
                scheduled_at    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'scheduled',
                target_count    INTEGER DEFAULT 0,
                delivered_count INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                sent_at         TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS campaign_messages (
                id           TEXT PRIMARY KEY,
                campaign_id  TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                session_id   TEXT,
                title        TEXT NOT NULL,
                message      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                delivered_at TEXT,
                is_seen      INTEGER DEFAULT 0,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            )
        """)


init_campaigns_db()


def _parse_amount(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    clean = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0


def get_all_users() -> List[str]:
    """Get all unique user IDs from wallets, bookings, and group members (case-insensitively deduplicated)."""
    user_map = {}  # lower_id -> original_id
    with _conn() as c:
        try:
            rows = c.execute("""
                SELECT DISTINCT user_id FROM wallets WHERE user_id IS NOT NULL AND user_id != '' AND user_id != 'dolphin_buddy'
                UNION
                SELECT DISTINCT user_id FROM bookings WHERE user_id IS NOT NULL AND user_id != ''
                UNION
                SELECT DISTINCT user_id FROM group_members WHERE user_id IS NOT NULL AND user_id != '' AND is_bot = 0 AND user_id != 'dolphin_buddy'
            """).fetchall()
            for r in rows:
                uid = str(r["user_id"]).strip()
                if uid:
                    user_map[uid.lower()] = uid
        except Exception:
            pass

    # Ensure defaults are added if not already present
    defaults = [
        "Agent_Prakhar",
        "Agent_Deepak",
        "Agent_Ananya",
        "Agent_Rahul",
        "Agent_Neha",
        "Agent_Vikram",
        "Agent_Pooja",
        "Agent_Karan",
    ]
    for d in defaults:
        if d.lower() not in user_map:
            user_map[d.lower()] = d

    return sorted(list(user_map.values()))


def evaluate_target_users(filter_type: str, filter_value: float = 0.0) -> List[str]:
    """Find user_ids matching the given filter criteria."""
    all_users = get_all_users()
    if filter_type == "all" or not filter_type:
        return all_users

    with _conn() as c:
        bookings = c.execute("SELECT user_id, premium FROM bookings").fetchall()

    user_totals: Dict[str, float] = {u: 0.0 for u in all_users}
    user_counts: Dict[str, int] = {u: 0 for u in all_users}

    for b in bookings:
        uid = b["user_id"]
        if uid in user_totals:
            user_totals[uid] += _parse_amount(b["premium"])
            user_counts[uid] += 1

    matched = []
    if filter_type == "min_booking_amount":
        for u in all_users:
            if user_totals.get(u, 0.0) >= filter_value:
                matched.append(u)
    elif filter_type == "min_policy_count":
        for u in all_users:
            if user_counts.get(u, 0) >= int(filter_value):
                matched.append(u)
    elif filter_type == "zero_bookings":
        for u in all_users:
            if user_counts.get(u, 0) == 0:
                matched.append(u)
    else:
        matched = all_users

    return matched if matched else all_users


def create_campaign(
    title: str,
    message: str,
    filter_type: str = "all",
    filter_value: float = 0.0,
    scheduled_at: Optional[str] = None,
) -> dict:
    """Create and schedule a new campaign."""
    now_dt = datetime.now(timezone.utc)
    cid = f"camp_{uuid.uuid4().hex[:10]}"
    
    if scheduled_at:
        sched_dt = _parse_iso_to_utc(scheduled_at) or now_dt
    else:
        sched_dt = now_dt

    sched_iso = sched_dt.isoformat()
    now_iso = now_dt.isoformat()

    targets = evaluate_target_users(filter_type, filter_value)

    with _conn() as c:
        c.execute("""
            INSERT INTO campaigns (
                id, title, message, filter_type, filter_value,
                scheduled_at, status, target_count, delivered_count,
                created_at, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, 0, ?, NULL)
        """, (cid, title, message, filter_type, filter_value, sched_iso, len(targets), now_iso))

    return get_campaign(cid)


def get_campaign(campaign_id: str) -> Optional[dict]:
    """Fetch single campaign by ID."""
    with _conn() as c:
        row = c.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        return dict(row) if row else None


def list_campaigns() -> List[dict]:
    """List all campaigns ordered by created_at descending."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign and associated messages."""
    with _conn() as c:
        c.execute("DELETE FROM campaign_messages WHERE campaign_id = ?", (campaign_id,))
        cur = c.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        return cur.rowcount > 0


def execute_campaign(campaign_id: str) -> dict:
    """
    Executes a scheduled or manual campaign.
    Dispatches message records to all target users.
    """
    camp = get_campaign(campaign_id)
    if not camp:
        return {"status": "not_found"}

    now = datetime.now(timezone.utc).isoformat()
    targets = evaluate_target_users(camp["filter_type"], camp["filter_value"])

    with _conn() as c:
        # Mark running
        c.execute("UPDATE campaigns SET status = 'running' WHERE id = ?", (campaign_id,))

        delivered = 0
        for uid in targets:
            mid = f"cmsg_{uuid.uuid4().hex[:10]}"
            # Dedicated campaign chat session per campaign
            sid = f"session_camp_{campaign_id[:8]}"

            c.execute("""
                INSERT INTO campaign_messages (
                    id, campaign_id, user_id, session_id, title, message, created_at, delivered_at, is_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (mid, campaign_id, uid, sid, camp["title"], camp["message"], now, now))
            delivered += 1

        c.execute("""
            UPDATE campaigns
            SET status = 'completed', delivered_count = ?, target_count = ?, sent_at = ?
            WHERE id = ?
        """, (delivered, len(targets), now, campaign_id))

    return get_campaign(campaign_id)


def _parse_iso_to_utc(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    clean = str(iso_str).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        try:
            from dateutil import parser
            dt = parser.parse(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None


def get_due_campaigns() -> List[dict]:
    """Find campaigns that are scheduled and due for execution."""
    now = datetime.now(timezone.utc)
    with _conn() as c:
        rows = c.execute("SELECT * FROM campaigns WHERE status = 'scheduled'").fetchall()
        due = []
        for r in rows:
            d = dict(r)
            sched_dt = _parse_iso_to_utc(d.get("scheduled_at"))
            if sched_dt and sched_dt <= now:
                due.append(d)
        return due


def get_user_campaign_messages(user_id: str, unseen_only: bool = False) -> List[dict]:
    """Retrieve campaign messages for a specific agent/user."""
    user_id = (user_id or "default_user").strip()
    with _conn() as c:
        if unseen_only:
            rows = c.execute(
                "SELECT * FROM campaign_messages WHERE user_id = ? AND is_seen = 0 ORDER BY created_at ASC",
                (user_id,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM campaign_messages WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def mark_campaign_messages_seen(user_id: str, message_ids: Optional[List[str]] = None):
    """Mark messages as seen by the user."""
    user_id = (user_id or "default_user").strip()
    with _conn() as c:
        if message_ids:
            placeholders = ",".join("?" for _ in message_ids)
            c.execute(
                f"UPDATE campaign_messages SET is_seen = 1 WHERE user_id = ? AND id IN ({placeholders})",
                [user_id] + message_ids,
            )
        else:
            c.execute(
                "UPDATE campaign_messages SET is_seen = 1 WHERE user_id = ?",
                (user_id,),
            )
