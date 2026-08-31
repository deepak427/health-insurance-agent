"""
Group Chat Data Layer — SQLite implementation for groups, members, messages, and read state.
"""
import sqlite3
import os
import json
import random
import string
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bookings.db")
BUDDY_USER_ID = "dolphin_buddy"
BUDDY_DISPLAY_NAME = "Dolphin Buddy"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str, length: int = 5) -> str:
    chars = string.ascii_uppercase + string.digits
    rand = "".join(random.choices(chars, k=length))
    return f"{prefix}_{rand}"


def init_groups_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                created_by  TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id    TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                display_name TEXT,
                is_bot      INTEGER NOT NULL DEFAULT 0,
                added_at    TEXT NOT NULL,
                added_by    TEXT NOT NULL,
                PRIMARY KEY (group_id, user_id),
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS group_messages (
                id          TEXT PRIMARY KEY,
                group_id    TEXT NOT NULL,
                sender_id   TEXT NOT NULL,
                sender_name TEXT,
                content     TEXT NOT NULL,
                msg_type    TEXT NOT NULL DEFAULT 'text',
                artifacts   TEXT,
                mentions    TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS group_unread (
                group_id    TEXT NOT NULL,
                user_id     TEXT NOT NULL,
                last_read   TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
                PRIMARY KEY (group_id, user_id)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_group_messages_group ON group_messages(group_id, created_at)")


init_groups_db()


def create_group(name: str, created_by: str, members: List[str], include_buddy: bool = True) -> Dict[str, Any]:
    group_id = _gen_id("grp", 6)
    now = _now()

    with _conn() as c:
        c.execute(
            "INSERT INTO groups (id, name, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (group_id, name.strip(), created_by.strip(), now, now),
        )

        all_members = set(m.strip() for m in members if m and m.strip())
        all_members.add(created_by.strip())

        for uid in all_members:
            c.execute(
                "INSERT OR IGNORE INTO group_members (group_id, user_id, display_name, is_bot, added_at, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, uid, uid, 0, now, created_by),
            )
            c.execute(
                "INSERT OR IGNORE INTO group_unread (group_id, user_id, last_read) VALUES (?, ?, ?)",
                (group_id, uid, now if uid == created_by else "1970-01-01T00:00:00Z"),
            )

        if include_buddy:
            c.execute(
                "INSERT OR IGNORE INTO group_members (group_id, user_id, display_name, is_bot, added_at, added_by) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, BUDDY_USER_ID, BUDDY_DISPLAY_NAME, 1, now, created_by),
            )

    return get_group(group_id)


def get_group(group_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        row = c.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not row:
            return None
        res = dict(row)

        members = c.execute(
            "SELECT user_id, display_name, is_bot, added_at, added_by FROM group_members WHERE group_id = ? ORDER BY is_bot ASC, added_at ASC",
            (group_id,),
        ).fetchall()
        res["members"] = [dict(m) for m in members]
        res["has_buddy"] = any(m["is_bot"] == 1 or m["user_id"] == BUDDY_USER_ID for m in res["members"])

        last_msg = c.execute(
            "SELECT * FROM group_messages WHERE group_id = ? ORDER BY created_at DESC LIMIT 1",
            (group_id,),
        ).fetchone()
        if last_msg:
            d_msg = dict(last_msg)
            d_msg["artifacts"] = json.loads(d_msg.get("artifacts") or "[]")
            d_msg["mentions"] = json.loads(d_msg.get("mentions") or "[]")
            res["last_message"] = d_msg
        else:
            res["last_message"] = None

    return res


def list_groups_for_user(user_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT g.*
            FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.user_id = ?
            ORDER BY g.updated_at DESC
            """,
            (user_id,),
        ).fetchall()

        groups = []
        for r in rows:
            g = dict(r)
            members = c.execute(
                "SELECT user_id, display_name, is_bot FROM group_members WHERE group_id = ?",
                (g["id"],),
            ).fetchall()
            g["members"] = [dict(m) for m in members]
            g["has_buddy"] = any(m["is_bot"] == 1 or m["user_id"] == BUDDY_USER_ID for m in g["members"])

            last_msg = c.execute(
                "SELECT * FROM group_messages WHERE group_id = ? ORDER BY created_at DESC LIMIT 1",
                (g["id"],),
            ).fetchone()
            if last_msg:
                g["last_message_preview"] = last_msg["content"]
                g["last_message_sender"] = last_msg["sender_name"] or last_msg["sender_id"]
                g["last_message_time"] = last_msg["created_at"]
            else:
                g["last_message_preview"] = "Group created"
                g["last_message_sender"] = g["created_by"]
                g["last_message_time"] = g["created_at"]

            unread_row = c.execute(
                "SELECT last_read FROM group_unread WHERE group_id = ? AND user_id = ?",
                (g["id"], user_id),
            ).fetchone()
            last_read = unread_row["last_read"] if unread_row else "1970-01-01T00:00:00Z"

            count_row = c.execute(
                "SELECT COUNT(*) AS cnt FROM group_messages WHERE group_id = ? AND created_at > ? AND sender_id != ?",
                (g["id"], last_read, user_id),
            ).fetchone()
            g["unread_count"] = count_row["cnt"] if count_row else 0
            groups.append(g)

    return groups


def delete_group(group_id: str, user_id: Optional[str] = None) -> bool:
    with _conn() as c:
        if user_id:
            row = c.execute("SELECT created_by FROM groups WHERE id = ?", (group_id,)).fetchone()
            if not row or row["created_by"] != user_id:
                return False
        c.execute("DELETE FROM group_messages WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM group_unread WHERE group_id = ?", (group_id,))
        c.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    return True


def add_member(group_id: str, user_id: str, added_by: str, is_bot: int = 0) -> bool:
    now = _now()
    with _conn() as c:
        if is_bot or user_id == BUDDY_USER_ID:
            existing_bot = c.execute(
                "SELECT COUNT(*) AS cnt FROM group_members WHERE group_id = ? AND (is_bot = 1 OR user_id = ?)",
                (group_id, BUDDY_USER_ID),
            ).fetchone()
            if existing_bot and existing_bot["cnt"] >= 1:
                return False
            user_id = BUDDY_USER_ID
            display_name = BUDDY_DISPLAY_NAME
            is_bot = 1
        else:
            display_name = user_id

        c.execute(
            "INSERT OR IGNORE INTO group_members (group_id, user_id, display_name, is_bot, added_at, added_by) VALUES (?, ?, ?, ?, ?, ?)",
            (group_id, user_id, display_name, is_bot, now, added_by),
        )
        c.execute(
            "INSERT OR IGNORE INTO group_unread (group_id, user_id, last_read) VALUES (?, ?, ?)",
            (group_id, user_id, "1970-01-01T00:00:00Z"),
        )
    return True


def remove_member(group_id: str, user_id: str) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id))
        c.execute("DELETE FROM group_unread WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    return True


def get_members(group_id: str) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT user_id, display_name, is_bot, added_at, added_by FROM group_members WHERE group_id = ? ORDER BY is_bot ASC, added_at ASC",
            (group_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def post_message(
    group_id: str,
    sender_id: str,
    content: str,
    sender_name: Optional[str] = None,
    msg_type: str = "text",
    artifacts: Optional[List[str]] = None,
    mentions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    msg_id = _gen_id("msg", 8)
    now = _now()
    art_json = json.dumps(artifacts or [])
    men_json = json.dumps(mentions or [])

    if not sender_name:
        sender_name = BUDDY_DISPLAY_NAME if sender_id == BUDDY_USER_ID else sender_id

    with _conn() as c:
        c.execute(
            """
            INSERT INTO group_messages (id, group_id, sender_id, sender_name, content, msg_type, artifacts, mentions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (msg_id, group_id, sender_id, sender_name, content, msg_type, art_json, men_json, now),
        )
        c.execute("UPDATE groups SET updated_at = ? WHERE id = ?", (now, group_id))
        if sender_id != BUDDY_USER_ID:
            c.execute(
                "INSERT INTO group_unread (group_id, user_id, last_read) VALUES (?, ?, ?) ON CONFLICT(group_id, user_id) DO UPDATE SET last_read = ?",
                (group_id, sender_id, now, now),
            )

    return {
        "id": msg_id,
        "group_id": group_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "content": content,
        "msg_type": msg_type,
        "artifacts": artifacts or [],
        "mentions": mentions or [],
        "created_at": now,
    }


def get_messages(group_id: str, limit: int = 50, before: Optional[str] = None) -> List[Dict[str, Any]]:
    with _conn() as c:
        if before:
            rows = c.execute(
                """
                SELECT * FROM group_messages
                WHERE group_id = ? AND created_at < (SELECT created_at FROM group_messages WHERE id = ?)
                ORDER BY created_at DESC LIMIT ?
                """,
                (group_id, before, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM group_messages WHERE group_id = ? ORDER BY created_at DESC LIMIT ?",
                (group_id, limit),
            ).fetchall()

    messages = []
    for r in reversed(rows):
        d = dict(r)
        d["artifacts"] = json.loads(d.get("artifacts") or "[]")
        d["mentions"] = json.loads(d.get("mentions") or "[]")
        messages.append(d)
    return messages


def mark_read(group_id: str, user_id: str) -> bool:
    now = _now()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO group_unread (group_id, user_id, last_read)
            VALUES (?, ?, ?)
            ON CONFLICT(group_id, user_id) DO UPDATE SET last_read = ?
            """,
            (group_id, user_id, now, now),
        )
    return True


def get_unread_count(group_id: str, user_id: str) -> int:
    with _conn() as c:
        unread_row = c.execute(
            "SELECT last_read FROM group_unread WHERE group_id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        last_read = unread_row["last_read"] if unread_row else "1970-01-01T00:00:00Z"

        count_row = c.execute(
            "SELECT COUNT(*) AS cnt FROM group_messages WHERE group_id = ? AND created_at > ? AND sender_id != ?",
            (group_id, last_read, user_id),
        ).fetchone()
        return count_row["cnt"] if count_row else 0


def get_all_unread_for_user(user_id: str) -> Dict[str, int]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT g.id AS group_id,
                   COUNT(m.id) AS cnt
            FROM groups g
            JOIN group_members gm ON g.id = gm.group_id AND gm.user_id = ?
            LEFT JOIN group_unread gu ON g.id = gu.group_id AND gu.user_id = ?
            LEFT JOIN group_messages m ON g.id = m.group_id
                AND m.created_at > COALESCE(gu.last_read, '1970-01-01T00:00:00Z')
                AND m.sender_id != ?
            GROUP BY g.id
            """,
            (user_id, user_id, user_id),
        ).fetchall()
        return {r["group_id"]: r["cnt"] for r in rows}
