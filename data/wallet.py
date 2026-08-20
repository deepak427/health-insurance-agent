"""
Wallet database operations — manages per-user credit balances in SQLite.
"""
import sqlite3
import os
import re
from datetime import datetime, timezone
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bookings.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_wallet_db():
    """Create wallets table if it doesn't exist."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                user_id    TEXT PRIMARY KEY,
                balance    REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            )
        """)


# Ensure table exists on import
init_wallet_db()


def parse_amount(val) -> float:
    """Extract float number from strings like '₹1,200', '1500.50', or numeric types."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    clean = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0


def get_wallet(user_id: str) -> dict:
    """Get wallet for user_id. Creates with 0 balance if not exists."""
    user_id = (user_id or "default_user").strip()
    with _conn() as c:
        row = c.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            now = datetime.now(timezone.utc).isoformat()
            c.execute("INSERT OR IGNORE INTO wallets (user_id, balance, updated_at) VALUES (?, 0.0, ?)", (user_id, now))
            row = c.execute("SELECT * FROM wallets WHERE user_id = ?", (user_id,)).fetchone()
        
        return {
            "user_id": row["user_id"],
            "balance": float(row["balance"]),
            "updated_at": row["updated_at"],
        }


def set_wallet_balance(user_id: str, balance: float) -> dict:
    """Set absolute balance for user_id."""
    user_id = (user_id or "default_user").strip()
    balance = max(0.0, float(balance))
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute("""
            INSERT INTO wallets (user_id, balance, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
        """, (user_id, balance, now))
    return get_wallet(user_id)


def add_wallet_credits(user_id: str, amount: float) -> dict:
    """Add credits to user's wallet."""
    user_id = (user_id or "default_user").strip()
    amount = max(0.0, float(amount))
    current = get_wallet(user_id)
    new_balance = current["balance"] + amount
    return set_wallet_balance(user_id, new_balance)


def deduct_wallet_credits(user_id: str, amount: float) -> tuple[bool, dict]:
    """
    Attempt to deduct amount from user's wallet.
    Returns (True, wallet) if sufficient balance, else (False, wallet).
    """
    user_id = (user_id or "default_user").strip()
    amount = max(0.0, float(amount))
    current = get_wallet(user_id)
    if current["balance"] < amount:
        return False, current
    
    new_balance = current["balance"] - amount
    updated = set_wallet_balance(user_id, new_balance)
    return True, updated
