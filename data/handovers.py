"""
Handovers Database Operations — Manages Internal & External human handovers
for group chats when custom policy structuring or agent assistance is requested.
"""
import sqlite3
import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bookings.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_handovers_db():
    """Create handovers table and migrate groups table if needed."""
    with _conn() as c:
        # Check / add handover_mode column to groups table
        try:
            c.execute("ALTER TABLE groups ADD COLUMN handover_mode TEXT NOT NULL DEFAULT 'internal'")
        except Exception:
            pass  # column already exists

        # Handovers table
        c.execute("""
            CREATE TABLE IF NOT EXISTS handovers (
                id              TEXT PRIMARY KEY,
                group_id        TEXT NOT NULL,
                group_name      TEXT NOT NULL,
                requester_id    TEXT NOT NULL,
                requester_name  TEXT NOT NULL,
                assigned_to     TEXT NOT NULL,
                mode            TEXT NOT NULL DEFAULT 'internal',
                requirement     TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                dm_session_id   TEXT,
                resolution_data TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)


init_handovers_db()


def set_group_handover_mode(group_id: str, mode: str) -> bool:
    """Set group handover mode ('internal' | 'external')."""
    mode = "external" if mode.lower() == "external" else "internal"
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        res = c.execute(
            "UPDATE groups SET handover_mode = ?, updated_at = ? WHERE id = ?",
            (mode, now, group_id)
        )
        return res.rowcount > 0


def get_group_handover_mode(group_id: str) -> str:
    """Get group handover mode (default 'internal')."""
    with _conn() as c:
        row = c.execute("SELECT handover_mode FROM groups WHERE id = ?", (group_id,)).fetchone()
        if row and row["handover_mode"]:
            return row["handover_mode"]
        return "internal"


def create_handover(
    group_id: str,
    group_name: str,
    requester_id: str,
    requester_name: str,
    assigned_to: str,
    mode: str,
    requirement: str,
) -> dict:
    """Create a new handover record."""
    hid = f"hnd_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    mode = "external" if mode.lower() == "external" else "internal"
    status = "pending" if mode == "external" else "assigned"
    dm_session_id = f"dm_handover_{hid}" if mode == "external" else None

    with _conn() as c:
        c.execute("""
            INSERT INTO handovers (
                id, group_id, group_name, requester_id, requester_name,
                assigned_to, mode, requirement, status, dm_session_id,
                resolution_data, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """, (
            hid, group_id, group_name, requester_id, requester_name,
            assigned_to, mode, requirement, status, dm_session_id,
            now, now
        ))

    return get_handover(hid)


def get_handover(handover_id: str) -> Optional[dict]:
    """Fetch single handover record by ID."""
    with _conn() as c:
        row = c.execute("SELECT * FROM handovers WHERE id = ?", (handover_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("resolution_data"):
            try:
                d["resolution_data"] = json.loads(d["resolution_data"])
            except Exception:
                pass
        return d


def list_handovers_for_group(group_id: str) -> List[dict]:
    """List all handovers for a group."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM handovers WHERE group_id = ? ORDER BY created_at DESC",
            (group_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("resolution_data"):
                try:
                    d["resolution_data"] = json.loads(d["resolution_data"])
                except Exception:
                    pass
            result.append(d)
        return result


def list_pending_handovers_for_user(user_id: str) -> List[dict]:
    """List pending external handovers assigned to a specific agent."""
    with _conn() as c:
        rows = c.execute(
            """
            SELECT * FROM handovers
            WHERE (LOWER(assigned_to) = LOWER(?) OR assigned_to = ?)
              AND mode = 'external'
              AND status IN ('pending', 'in_consultation')
            ORDER BY created_at DESC
            """,
            (user_id, user_id)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("resolution_data"):
                try:
                    d["resolution_data"] = json.loads(d["resolution_data"])
                except Exception:
                    pass
            result.append(d)
        return result


def approve_handover(
    handover_id: str,
    approved_by: str,
    resolution_data: dict,
) -> Optional[dict]:
    """
    Approve an external handover.
    Updates handover status to 'approved', stores resolution_data,
    and automatically publishes the approved custom policy into group_messages.
    """
    from data.groups import post_message, BUDDY_USER_ID, BUDDY_DISPLAY_NAME

    now = datetime.now(timezone.utc).isoformat()
    h = get_handover(handover_id)
    if not h:
        return None

    res_str = json.dumps(resolution_data)
    with _conn() as c:
        c.execute("""
            UPDATE handovers
            SET status = 'approved', resolution_data = ?, updated_at = ?
            WHERE id = ?
        """, (res_str, now, handover_id))

    # Format custom policy card marker
    plan_name = resolution_data.get("plan_name", "Custom Structured Plan")
    insurer = resolution_data.get("insurer", "Specialized Underwriting")
    premium = resolution_data.get("premium", "₹3,500")
    sum_insured = resolution_data.get("sum_insured", "$100,000")
    destination = resolution_data.get("destination", "Global / Multi-country")
    travel_dates = resolution_data.get("travel_dates", "Flexible")
    riders = resolution_data.get("riders", "Standard + Adventure + Medical Waiver")
    notes = resolution_data.get("notes", "Approved by senior agent underwriter.")
    clean_premium = str(premium).replace("₹", "").replace(",", "").strip()

    policy_card = {
        "type": "policy",
        "name": plan_name,
        "title": plan_name,
        "company": insurer,
        "insurer": insurer,
        "premium": clean_premium if clean_premium else "3,500",
        "price": premium,
        "sumInsured": sum_insured,
        "sum_insured": sum_insured,
        "badge": "Custom Structured",
        "highlights": [
            f"Coverage: {sum_insured}",
            f"Destination: {destination}",
            f"Validity: {travel_dates}",
            f"Included Riders: {riders}",
            f"Notes: {notes}",
        ],
        "features": [
            f"Coverage: {sum_insured}",
            f"Destination: {destination}",
            f"Validity: {travel_dates}",
            f"Included Riders: {riders}",
            f"Notes: {notes}",
        ],
        "action": "Choose this plan",
        "prompt": f"I want to book the {plan_name} plan from {insurer} for ₹{clean_premium}",
    }

    cards_marker = f"<!--POLICY_CARDS:[{json.dumps(policy_card)}]-->"

    group_announcement = (
        f"✨ Here is the customized policy option structured for you, **@{requester_name}**:\n\n"
        f"{cards_marker}\n\n"
        f"@{requester_name} You can click **Choose Plan** above to confirm this custom structured booking with your wallet credits."
    )

    # Post message into group
    try:
        post_message(
            group_id=h["group_id"],
            sender_id=BUDDY_USER_ID,
            content=group_announcement,
            sender_name=BUDDY_DISPLAY_NAME,
            msg_type="bot_response",
            mentions=[requester_id, approved_by] if requester_id else [approved_by]
        )
    except Exception as e:
        print(f"[approve_handover] Failed to post to group: {e}")

    return get_handover(handover_id)
