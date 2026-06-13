"""
Idempotent SQLite migration — safe to run multiple times.
Brings any existing database.db up to the latest schema, then seeds a default admin.

Usage:
    cd backend/backend && python3 migrate_admin.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime

from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db"),
)

ADMIN_EMAIL    = "admin@solardecide.dz"
ADMIN_PASSWORD = "Admin2026"
ADMIN_NAME     = "Administrator"


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    )
    return cur.fetchone() is not None


def _bootstrap_via_sqlalchemy() -> bool:
    """Creates database.db via SQLAlchemy create_all() when the file is missing entirely."""
    if os.path.exists(DB_PATH):
        return True
    print("📂 database.db missing — bootstrapping via SQLAlchemy create_all()…")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from flask import Flask
        from db_models import db
        app = Flask("migrator")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)
        with app.app_context():
            db.create_all()
        print(f"  ✓ database.db created at {DB_PATH}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Could not bootstrap database.db automatically: {exc}")
        print("   → start the Flask app once with `python3 app.py`, then re-run.")
        return False


def migrate(db_path: str = DB_PATH) -> None:
    print(f"📂 SQLite : {db_path}")
    if not os.path.exists(db_path):
        if not _bootstrap_via_sqlalchemy():
            return

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    if not _table_exists(cur, "users"):
        print("⚠️  'users' table still missing after bootstrap — aborting.")
        conn.close()
        return

    # Subscription columns
    subscription_columns = [
        ("plan",                        "TEXT     NOT NULL DEFAULT 'free'"),
        ("plan_expires_at",             "DATETIME"),
        ("analyses_count_month",        "INTEGER  NOT NULL DEFAULT 0"),
        ("recommandations_count_month", "INTEGER  NOT NULL DEFAULT 0"),
        ("counters_reset_at",           "DATETIME"),
    ]
    for col, ddl in subscription_columns:
        if not _column_exists(cur, "users", col):
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            print(f"  ✓ users.{col} added")
        else:
            print(f"  · users.{col} already present")

    # Admin columns
    admin_columns = [
        ("role",       "TEXT NOT NULL DEFAULT 'user'"),
        ("is_active",  "INTEGER NOT NULL DEFAULT 1"),
        ("last_login", "DATETIME"),
    ]
    for col, ddl in admin_columns:
        if not _column_exists(cur, "users", col):
            cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            print(f"  ✓ users.{col} added")
        else:
            print(f"  · users.{col} already present")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS error_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT    NOT NULL,
            page       TEXT,
            user_id    INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✓ error_logs table ready")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            action     TEXT    NOT NULL,
            details    TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✓ activity_logs table ready")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_logs(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_action     ON activity_logs(action)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_error_created_at    ON error_logs(created_at)")

    cur.execute("SELECT id, role, plan FROM users WHERE email = ?", (ADMIN_EMAIL,))
    row = cur.fetchone()
    if row is None:
        pwd_hash = generate_password_hash(ADMIN_PASSWORD)
        from datetime import timezone as _tz
        now = datetime.now(_tz.utc).replace(tzinfo=None)  # naive UTC — SQLite has no tz support
        cur.execute("""
            INSERT INTO users
                (name, email, password_hash, role, plan, is_active, created_at,
                 analyses_count_month, recommandations_count_month)
            VALUES (?, ?, ?, 'admin', 'enterprise', 1, ?, 0, 0)
        """, (ADMIN_NAME, ADMIN_EMAIL, pwd_hash, now))
        print(f"  ✓ admin seeded : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    else:
        # Promote existing account if it was previously created as a regular user
        updates = []
        if row[1] != "admin":
            updates.append("role = 'admin'")
        if row[2] != "enterprise":
            updates.append("plan = 'enterprise'")
        if updates:
            updates.append("is_active = 1")
            cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", (row[0],))
            print(f"  ✓ promoted existing user to admin : {ADMIN_EMAIL}")
        else:
            print(f"  · admin {ADMIN_EMAIL} already present")

    conn.commit()
    conn.close()
    print("✅ Migration terminée")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Erreur : {exc}", file=sys.stderr)
        sys.exit(1)