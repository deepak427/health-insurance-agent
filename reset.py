"""
reset.py — wipes all session history and artifacts so you can start fresh.

Run from the hip/ directory:
    python reset.py
"""

import os
import shutil
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent / "my_agent" / ".adk"
SESSION_DB = BASE / "session.db"
ARTIFACTS_DIR = BASE / "artifacts"


def reset_sessions():
    if not SESSION_DB.exists():
        print("  session.db not found — skipping")
        return
    conn = sqlite3.connect(SESSION_DB)
    cursor = conn.cursor()
    # List tables and clear them all
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        print(f"  Cleared table: {table}")
    conn.commit()
    conn.close()
    print("  Sessions cleared.")


def reset_artifacts():
    if not ARTIFACTS_DIR.exists():
        print("  Artifacts directory not found — skipping")
        return
    count = 0
    for item in ARTIFACTS_DIR.rglob("*"):
        if item.is_file():
            item.unlink()
            count += 1
    # Remove empty dirs (keep the root artifacts/ folder itself)
    for item in sorted(ARTIFACTS_DIR.rglob("*"), reverse=True):
        if item.is_dir() and not any(item.iterdir()):
            item.rmdir()
    print(f"  Removed {count} artifact file(s).")


if __name__ == "__main__":
    print("Resetting HIP agent data...\n")

    print("[1/2] Sessions (session.db):")
    reset_sessions()

    print("\n[2/2] Artifacts:")
    reset_artifacts()

    print("\nDone. Start fresh!")
