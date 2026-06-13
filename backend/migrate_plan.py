#!/usr/bin/env python3
"""
One-shot migration

Adds the following columns to the SQLite `users` table if they don't yet exist:
    plan                         TEXT     DEFAULT 'free'
    plan_expires_at              DATETIME
    analyses_count_month         INTEGER  DEFAULT 0
    recommandations_count_month  INTEGER  DEFAULT 0
    counters_reset_at            DATETIME

Run once after pulling the Phase 2 code:

    cd backend/backend
    python migrate_plan.py

Idempotent — safe to re-run; existing columns are kept as-is.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "database.db"

NEW_COLUMNS = [
    ("plan",                         "TEXT NOT NULL DEFAULT 'free'"),
    ("plan_expires_at",              "DATETIME"),
    ("analyses_count_month",         "INTEGER NOT NULL DEFAULT 0"),
    ("recommandations_count_month",  "INTEGER NOT NULL DEFAULT 0"),
    ("counters_reset_at",            "DATETIME"),
]


def main() -> int:
    if not DB_PATH.exists():
        print(f"⚠  Database not found at {DB_PATH}")
        print("   Start the app once to let Flask create it, then re-run this script.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cur.fetchone():
        print("⚠  Table 'users' does not exist — nothing to migrate.")
        return 1

    # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
    existing = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    added = []
    skipped = []
    for col, defn in NEW_COLUMNS:
        if col in existing:
            skipped.append(col)
            continue
        cur.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
        added.append(col)

    # Backfill existing rows so counters_reset_at is never NULL after migration
    now_iso = datetime.utcnow().isoformat()
    cur.execute(
        "UPDATE users SET counters_reset_at = ? WHERE counters_reset_at IS NULL",
        (now_iso,),
    )

    conn.commit()
    conn.close()

    print("✓ Migration completed.")
    if added:
        print(f"  Added columns:   {', '.join(added)}")
    if skipped:
        print(f"  Already present: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())