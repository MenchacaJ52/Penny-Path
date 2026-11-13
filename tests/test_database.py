"""PostgreSQL-specific behavior: exact money, constraints, concurrency, and migration."""
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))


def _user(db, name="u"):
    db.create_user(name, "hash")
    return db.get_user(name)[0]


def test_money_is_stored_exactly(db):
    uid = _user(db)
    db.save_account("checking", 0.1 + 0.2, uid)          # 0.30000000000000004 as a float
    assert db.load_account("checking", uid) == 0.3       # NUMERIC(14,2) keeps exact cents
    assert isinstance(db.load_account("checking", uid), float)


def test_duplicate_username_is_rejected(db):
    assert db.create_user("same", "h") is True
    assert db.create_user("same", "h") is False


def test_constraints_reject_impossible_values(db):
    uid = _user(db)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.save_expense("needs", "rent/mortgage", "Rent", -5, "Monthly", uid)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.save_expense("snacks", "other", "Chips", 5, "Monthly", uid)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.save_expense("needs", "groceries", "Food", 5, "Monthly", 99999)


def test_debt_total_tracks_itemized_debts(db):
    uid = _user(db)
    a = db.add_debt(uid, "Card", 1000, 20, 50)
    db.add_debt(uid, "Loan", 500.55, 5, 25)
    assert db.load_debt(uid) == pytest.approx(1500.55)
    db.delete_debt(a, uid)
    assert db.load_debt(uid) == pytest.approx(500.55)


def test_profile_upsert(db):
    uid = _user(db)
    db.save_profile(uid, {"age": 30, "full_name": "A", "not_a_field": "ignored"})
    db.save_profile(uid, {"household_size": 3})
    p = db.load_profile(uid)
    assert (p["age"], p["full_name"], p["household_size"]) == (30, "A", 3)


def test_pool_handles_concurrent_requests(db):
    uid = _user(db)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda i: db.save_expense("wants", "hobbies", f"e{i}", i + 1,
                                                      "Monthly", uid), range(40)))
    assert len(set(ids)) == 40 and len(db.load_expenses(uid)) == 40


def test_migrate_from_old_sqlite_schema(db, tmp_path):
    """An old-format SQLite file (no `onboarded`/`subcategory`, an orphaned row) migrates
    completely, keeps ids, and new rows continue numbering after the copied ones."""
    from migrate_sqlite_to_postgres import migrate

    src = tmp_path / "old.db"
    con = sqlite3.connect(src)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT,
                            created_at TEXT);
        CREATE TABLE expenses (id INTEGER PRIMARY KEY, user_id INTEGER, category TEXT,
                               name TEXT, amount REAL, frequency TEXT);
        CREATE TABLE accounts (id TEXT, user_id INTEGER, balance REAL);
        INSERT INTO users VALUES (7, 'old_user', 'legacyhash', '2026-05-04 12:00:00');
        INSERT INTO expenses VALUES (40, 7, 'needs', 'Rent', 1200.5, 'Monthly');
        INSERT INTO expenses VALUES (41, 99, 'wants', 'Orphan', 10, 'Monthly');
        INSERT INTO accounts VALUES ('savings', 7, 2500.25);
    """)
    con.commit(); con.close()

    result = migrate(str(src), url=db.url, schema=db._kwargs["options"].split("=")[1])
    assert result["copied"]["users"] == 1 and result["copied"]["expenses"] == 1
    assert result["skipped_orphans"] == {"expenses": 1}

    user = db.get_user("old_user")
    assert user[0] == 7 and user[3] is False                  # id kept, onboarded defaulted
    assert db.load_expenses(7) == [(40, "needs", "other", "Rent", 1200.5, "Monthly")]
    assert db.load_account("savings", 7) == 2500.25
    # Numbering continues after the highest copied id (40; the orphan 41 wasn't copied).
    assert db.save_expense("needs", "groceries", "New", 5, "Monthly", 7) == 41

    with pytest.raises(SystemExit):                            # never migrates twice
        migrate(str(src), url=db.url, schema=db._kwargs["options"].split("=")[1])
