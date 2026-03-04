import sqlite3


class Database:
    DB_FILE = "pennypath.db"

    def __init__(self):
        self.conn = sqlite3.connect(self.DB_FILE)
        self._create_tables()

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
        """Returns (id, username, password_hash) or None."""
        return self.conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()

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
                     frequency: str, user_id: int):
        self.conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, name, amount, frequency) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, category, subcategory, name, amount, frequency)
        )
        self.conn.commit()

    def load_expenses(self, user_id: int) -> list:
        return self.conn.execute(
            "SELECT category, subcategory, name, amount, frequency FROM expenses WHERE user_id = ?",
            (user_id,)
        ).fetchall()

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
    def save_session(self, savings_bal, checking_bal, wage, budget_amt, user_id: int):
        self.save_account("savings",  savings_bal,  user_id)
        self.save_account("checking", checking_bal, user_id)
        self.save_wage(wage, user_id)
        if budget_amt is not None:
            self.save_budget(budget_amt, user_id)

    def load_session(self, user_id: int):
        return {
            "savings":  self.load_account("savings",  user_id),
            "checking": self.load_account("checking", user_id),
            "wage":     self.load_wage(user_id),
            "budget":   self.load_budget(user_id),
            "expenses": self.load_expenses(user_id),
        }

    def close(self):
        self.conn.close()
