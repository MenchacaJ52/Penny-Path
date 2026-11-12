import os
import sqlite3
import threading

from pennypath.paths import DEFAULT_DB


class Database:
    """SQLite persistence for all three front ends (CLI, desktop, web).

    Each thread gets its own connection, so the Flask dev server (which handles
    requests on multiple threads) never shares a connection between requests.
    The file defaults to pennypath.db in the project root; override with the
    PENNYPATH_DB environment variable or the `path` argument (used by tests).
    """

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("PENNYPATH_DB") or DEFAULT_DB
        self._local = threading.local()
        self._create_tables()

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path)
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def _create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS accounts (
                id      TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS wages (
                user_id     INTEGER PRIMARY KEY,
                weekly_wage REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category    TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT 'other',
                name        TEXT NOT NULL,
                amount      REAL NOT NULL,
                frequency   TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS budget (
                user_id INTEGER PRIMARY KEY,
                amount  REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS chat_feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                question   TEXT NOT NULL,
                response   TEXT NOT NULL,
                reward     INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS debt (
                user_id INTEGER PRIMARY KEY,
                amount  REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS debts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                balance     REAL NOT NULL,
                apr         REAL NOT NULL,
                min_payment REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS profiles (
                user_id        INTEGER PRIMARY KEY,
                full_name      TEXT NOT NULL DEFAULT '',
                age            INTEGER,
                email          TEXT NOT NULL DEFAULT '',
                occupation     TEXT NOT NULL DEFAULT '',
                state          TEXT NOT NULL DEFAULT '',
                household_size INTEGER,
                primary_goal   TEXT NOT NULL DEFAULT '',
                risk_tolerance TEXT NOT NULL DEFAULT '',
                pay_frequency  TEXT NOT NULL DEFAULT 'weekly',
                updated_at     TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        """Apply any schema upgrades needed for existing databases."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "subcategory" not in cols:
            self.conn.execute(
                "ALTER TABLE expenses ADD COLUMN subcategory TEXT NOT NULL DEFAULT 'other'"
            )
            self.conn.commit()

        user_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(users)").fetchall()]
        if "onboarded" not in user_cols:
            self.conn.execute("ALTER TABLE users ADD COLUMN onboarded INTEGER NOT NULL DEFAULT 0")
            self.conn.commit()
            # existing users who already have a wage are already set up — skip their survey
            self.conn.execute("""
                UPDATE users SET onboarded = 1
                WHERE id IN (SELECT user_id FROM wages WHERE weekly_wage > 0)
            """)
            self.conn.commit()

        tables = [r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "chat_feedback" not in tables:
            self.conn.execute("""
                CREATE TABLE chat_feedback (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    question   TEXT NOT NULL,
                    response   TEXT NOT NULL,
                    reward     INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            self.conn.commit()

    def create_user(self, username: str, password_hash: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # username taken

    def get_user(self, username: str):
        """Returns (id, username, password_hash, onboarded) or None."""
        return self.conn.execute(
            "SELECT id, username, password_hash, onboarded FROM users WHERE username = ?",
            (username,)
        ).fetchone()

    def get_password_hash(self, user_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None

    def update_password(self, user_id: int, password_hash: str):
        self.conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                          (password_hash, user_id))
        self.conn.commit()

    def mark_onboarded(self, user_id: int):
        self.conn.execute("UPDATE users SET onboarded = 1 WHERE id = ?", (user_id,))
        self.conn.commit()

    # ── Accounts ──────────────────────────────────────────────────────────
    def save_account(self, account_id: str, balance: float, user_id: int):
        self.conn.execute(
            "INSERT INTO accounts (id, user_id, balance) VALUES (?, ?, ?) "
            "ON CONFLICT(id, user_id) DO UPDATE SET balance = excluded.balance",
            (account_id, user_id, balance)
        )
        self.conn.commit()

    def load_account(self, account_id: str, user_id: int) -> float:
        row = self.conn.execute(
            "SELECT balance FROM accounts WHERE id = ? AND user_id = ?",
            (account_id, user_id)
        ).fetchone()
        return row[0] if row else 0.0

    # ── Wages ─────────────────────────────────────────────────────────────
    def save_wage(self, weekly_wage: float, user_id: int):
        self.conn.execute(
            "INSERT INTO wages (user_id, weekly_wage) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET weekly_wage = excluded.weekly_wage",
            (user_id, weekly_wage)
        )
        self.conn.commit()

    def load_wage(self, user_id: int) -> float:
        row = self.conn.execute(
            "SELECT weekly_wage FROM wages WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0.0

    # ── Expenses ──────────────────────────────────────────────────────────
    def save_expense(self, category: str, subcategory: str, name: str, amount: float,
                     frequency: str, user_id: int) -> int:
        """Insert an expense and return its new id."""
        cur = self.conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, name, amount, frequency) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, category, subcategory, name, amount, frequency)
        )
        self.conn.commit()
        return cur.lastrowid

    def load_expenses(self, user_id: int) -> list:
        """Rows of (id, category, subcategory, name, amount, frequency), oldest first."""
        return self.conn.execute(
            "SELECT id, category, subcategory, name, amount, frequency "
            "FROM expenses WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall()

    def update_expense(self, expense_id: int, user_id: int, category: str, subcategory: str,
                       name: str, amount: float, frequency: str) -> bool:
        cur = self.conn.execute(
            "UPDATE expenses SET category = ?, subcategory = ?, name = ?, amount = ?, frequency = ? "
            "WHERE id = ? AND user_id = ?",
            (category, subcategory, name, amount, frequency, expense_id, user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_expense(self, expense_id: int, user_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def clear_expenses(self, user_id: int):
        self.conn.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # ── Budget ────────────────────────────────────────────────────────────
    def save_budget(self, amount: float, user_id: int):
        self.conn.execute(
            "INSERT INTO budget (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount",
            (user_id, amount)
        )
        self.conn.commit()

    def load_budget(self, user_id: int) -> float:
        row = self.conn.execute(
            "SELECT amount FROM budget WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0.0

    # ── Session helpers ───────────────────────────────────────────────────
    def save_session(self, savings_bal, checking_bal, wage, budget_amt, user_id: int,
                     wage_account_bal: float | None = None):
        self.save_account("savings",  savings_bal,  user_id)
        self.save_account("checking", checking_bal, user_id)
        self.save_wage(wage, user_id)
        if budget_amt is not None:
            self.save_budget(budget_amt, user_id)
        if wage_account_bal is not None:
            self.save_account("wage", wage_account_bal, user_id)

    def load_session(self, user_id: int):
        return {
            "savings":  self.load_account("savings",  user_id),
            "checking": self.load_account("checking", user_id),
            "wage_account": self.load_account("wage", user_id),
            "wage":     self.load_wage(user_id),
            "budget":   self.load_budget(user_id),
            "expenses": self.load_expenses(user_id),
            "debt":     self.load_debt(user_id),
        }

    # ── Chat feedback (RL) ────────────────────────────────────────────────
    def save_feedback(self, user_id: int, question: str, response: str, reward: int):
        """Store a thumbs-up (+1) or thumbs-down (-1) rating for a Q&A pair."""
        self.conn.execute(
            "INSERT INTO chat_feedback (user_id, question, response, reward) "
            "VALUES (?, ?, ?, ?)",
            (user_id, question, response, reward)
        )
        self.conn.commit()

    def get_positive_feedback(self, user_id: int, limit: int = 50) -> list:
        """Return (question, response) pairs the user rated positively, newest first."""
        return self.conn.execute(
            "SELECT question, response FROM chat_feedback "
            "WHERE user_id = ? AND reward > 0 "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()

    # ── Debt ──────────────────────────────────────────────────────────────
    def save_debt(self, amount: float, user_id: int):
        self.conn.execute(
            "INSERT INTO debt (user_id, amount) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount",
            (user_id, amount)
        )
        self.conn.commit()

    # ── Itemized debts (Debt Plan) ────────────────────────────────────────
    # When a user has itemized debts, their total is kept in sync with the
    # single `debt` figure shown on the dashboard.
    def load_debts(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, balance, apr, min_payment FROM debts WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall()
        return [dict(id=r[0], name=r[1], balance=r[2], apr=r[3], min_payment=r[4]) for r in rows]

    def _sync_debt_total(self, user_id: int):
        total = self.conn.execute(
            "SELECT COALESCE(SUM(balance), 0) FROM debts WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        self.save_debt(total, user_id)

    def add_debt(self, user_id: int, name: str, balance: float, apr: float,
                 min_payment: float) -> int:
        cur = self.conn.execute(
            "INSERT INTO debts (user_id, name, balance, apr, min_payment) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, balance, apr, min_payment)
        )
        self.conn.commit()
        self._sync_debt_total(user_id)
        return cur.lastrowid

    def delete_debt(self, debt_id: int, user_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM debts WHERE id = ? AND user_id = ?",
                                (debt_id, user_id))
        self.conn.commit()
        self._sync_debt_total(user_id)
        return cur.rowcount > 0

    def load_debt(self, user_id: int) -> float:
        row = self.conn.execute(
            "SELECT amount FROM debt WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0.0

    # ── Profile ───────────────────────────────────────────────────────────
    PROFILE_FIELDS = ("full_name", "age", "email", "occupation", "state",
                      "household_size", "primary_goal", "risk_tolerance", "pay_frequency")

    def load_profile(self, user_id: int) -> dict:
        row = self.conn.execute(
            f"SELECT {', '.join(self.PROFILE_FIELDS)} FROM profiles WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if row is None:
            return {f: None if f in ("age", "household_size") else "" for f in self.PROFILE_FIELDS} \
                   | {"pay_frequency": "weekly"}
        return dict(zip(self.PROFILE_FIELDS, row))

    def save_profile(self, user_id: int, fields: dict):
        """Upsert any subset of PROFILE_FIELDS."""
        fields = {k: v for k, v in fields.items() if k in self.PROFILE_FIELDS}
        if not fields:
            return
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        self.conn.execute(
            f"INSERT INTO profiles (user_id, {cols}) VALUES (?, {marks}) "
            f"ON CONFLICT(user_id) DO UPDATE SET {updates}, updated_at = datetime('now')",
            (user_id, *fields.values())
        )
        self.conn.commit()

    def close(self):
        """Close this thread's connection (a new one opens on next use)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
