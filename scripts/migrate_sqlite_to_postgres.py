"""
migrate_sqlite_to_postgres.py  —  Copy data from the old SQLite file into PostgreSQL.

    python scripts/migrate_sqlite_to_postgres.py                     # reads pennypath.db
    python scripts/migrate_sqlite_to_postgres.py --sqlite other.db

Uses DATABASE_URL for the target. Runs in one transaction (all or nothing),
keeps row ids so references stay intact, and refuses to run if the target
already has users. The SQLite file is only read, never modified.
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root

import psycopg  # noqa: E402

from pennypath.database import Database, describe  # noqa: E402
from pennypath.paths import LEGACY_SQLITE_DB  # noqa: E402

# Target columns per table, in insert order. Missing source columns get these defaults
# (older PennyPath databases predate `onboarded` and `subcategory`).
TABLES = {
    "users":         ["id", "username", "password_hash", "onboarded", "created_at"],
    "accounts":      ["id", "user_id", "balance"],
    "wages":         ["user_id", "weekly_wage"],
    "expenses":      ["id", "user_id", "category", "subcategory", "name", "amount", "frequency"],
    "budget":        ["user_id", "amount"],
    "chat_feedback": ["id", "user_id", "question", "response", "reward", "created_at"],
    "debt":          ["user_id", "amount"],
    "debts":         ["id", "user_id", "name", "balance", "apr", "min_payment"],
    "profiles":      ["user_id", "full_name", "age", "email", "occupation", "state",
                      "household_size", "primary_goal", "risk_tolerance", "pay_frequency"],
}
DEFAULTS = {"onboarded": 0, "subcategory": "other", "created_at": None}
IDENTITY_TABLES = ["users", "expenses", "chat_feedback", "debts"]


def read_sqlite(path: str) -> dict[str, list[dict]]:
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)   # read-only
    existing = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    data = {}
    for table, cols in TABLES.items():
        if table not in existing:
            data[table] = []
            continue
        have = {r[1] for r in src.execute(f"PRAGMA table_info({table})")}
        select = ", ".join(c if c in have else "NULL" for c in cols)
        rows = src.execute(f"SELECT {select} FROM {table}").fetchall()
        data[table] = [{c: (row[i] if c in have else DEFAULTS.get(c)) for i, c in enumerate(cols)}
                       for row in rows]
    src.close()
    return data


def clean(table: str, row: dict) -> dict:
    if table == "users":
        row["onboarded"] = bool(row["onboarded"])
        # SQLite's datetime('now') is UTC text with no zone; tell Postgres so.
        row["created_at"] = f"{row['created_at']}+00" if row["created_at"] else None
    if table == "chat_feedback" and row["created_at"]:
        row["created_at"] = f"{row['created_at']}+00"
    return row


def migrate(sqlite_path: str, url: str | None = None, schema: str | None = None) -> dict:
    db = Database(url, schema=schema)
    db.ensure_ready()                      # creates the tables if needed
    data = read_sqlite(sqlite_path)
    user_ids = {u["id"] for u in data["users"]}
    counts, skipped = {}, {}

    with psycopg.connect(db.url, **db._kwargs) as conn:     # one transaction
        if conn.execute("SELECT EXISTS (SELECT 1 FROM users)").fetchone()[0]:
            raise SystemExit("The target database already has users — refusing to migrate "
                             "twice. Point DATABASE_URL at an empty database.")
        for table, cols in TABLES.items():
            rows = [clean(table, r) for r in data[table]]
            if table != "users":           # drop orphans left behind by deleted users
                kept = [r for r in rows if r["user_id"] in user_ids]
                skipped[table] = len(rows) - len(kept)
                rows = kept
            if not rows:
                counts[table] = 0
                continue
            # Let Postgres fill created_at when the old row had none.
            use = [c for c in cols if not (c == "created_at" and all(r[c] is None for r in rows))]
            query = f"INSERT INTO {table} ({', '.join(use)}) VALUES ({', '.join(['%s'] * len(use))})"
            with conn.cursor() as cur:
                cur.executemany(query, [[r[c] for c in use] for r in rows])
            counts[table] = len(rows)
        for table in IDENTITY_TABLES:      # continue numbering after the copied ids
            conn.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                         f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}")
    db.close()
    return {"copied": counts, "skipped_orphans": {t: n for t, n in skipped.items() if n}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy PennyPath data from SQLite to PostgreSQL.")
    parser.add_argument("--sqlite", default=LEGACY_SQLITE_DB,
                        help="SQLite file to read (default: pennypath.db)")
    args = parser.parse_args()
    if not os.path.exists(args.sqlite):
        raise SystemExit(f"No SQLite file at {args.sqlite}")
    result = migrate(args.sqlite)
    print(f"Copied into {describe(os.environ.get('DATABASE_URL', ''))}:")
    for table, n in result["copied"].items():
        print(f"  {table:<14} {n} rows")
    for table, n in result["skipped_orphans"].items():
        print(f"  (skipped {n} {table} rows belonging to users that no longer exist)")
