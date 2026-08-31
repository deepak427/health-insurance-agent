"""
Token usage tracking — stores per-call token counts in SQLite.
Each row = one LLM call (one after_model_callback invocation).
"""
import sqlite3
import os
from datetime import datetime, timezone

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bookings.db")

# Gemini 3.5 Flash pricing — Paid Tier (USD per 1M tokens)
# Source: ai.google.dev/gemini-api/docs/pricing
_INPUT_PRICE_PER_M = 1.50
_OUTPUT_PRICE_PER_M = 9.00


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT NOT NULL,
                session_id      TEXT NOT NULL,
                prompt_tokens   INTEGER NOT NULL DEFAULT 0,
                output_tokens   INTEGER NOT NULL DEFAULT 0,
                total_tokens    INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_token_session ON token_usage(user_id, session_id)")


_init()


def record_usage(user_id: str, session_id: str, prompt_tokens: int, output_tokens: int):
    """Insert one token usage row."""
    total = prompt_tokens + output_tokens
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as c:
        c.execute(
            "INSERT INTO token_usage (user_id, session_id, prompt_tokens, output_tokens, total_tokens, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, session_id, prompt_tokens, output_tokens, total, now),
        )


def get_session_usage(user_id: str, session_id: str) -> dict:
    """Aggregate token usage for a session and compute estimated cost."""
    with _conn() as c:
        row = c.execute(
            """
            SELECT
                COALESCE(SUM(prompt_tokens), 0)  AS prompt_tokens,
                COALESCE(SUM(output_tokens), 0)  AS output_tokens,
                COALESCE(SUM(total_tokens), 0)   AS total_tokens,
                COUNT(*)                          AS call_count
            FROM token_usage
            WHERE user_id = ? AND session_id = ?
            """,
            (user_id, session_id),
        ).fetchone()

    prompt = row["prompt_tokens"]
    output = row["output_tokens"]
    total = row["total_tokens"]
    calls = row["call_count"]

    cost_usd = (prompt / 1_000_000 * _INPUT_PRICE_PER_M) + (output / 1_000_000 * _OUTPUT_PRICE_PER_M)

    return {
        "user_id": user_id,
        "session_id": session_id,
        "prompt_tokens": prompt,
        "output_tokens": output,
        "total_tokens": total,
        "llm_call_count": calls,
        "estimated_cost_usd": round(cost_usd, 6),
        "model": "gemini-3.5-flash",
        "pricing_note": "$1.50/M input · $9.00/M output (Paid Tier)",
    }
