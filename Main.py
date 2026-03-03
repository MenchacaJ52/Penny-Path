import time
import hashlib
import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.model_selection import train_test_split
import numpy as np
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


# ── Authentication ────────────────────────────────────────────────────────────
class UserAuth:
    """Handles user registration and login with SHA-256 password hashing."""

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = "pennypath_salt_2024"   # static salt (upgrade to bcrypt for production)
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    def register(self, db: Database) -> dict | None:
        """Prompt for new credentials, create account. Returns user dict or None."""
        print("\n\033[32m─── REGISTER ───\033[0m")
        username = input("Choose a username: ").strip()
        if not username:
            print("\033[31mUsername cannot be empty.\033[0m")
            return None

        # Check if taken
        if db.get_user(username):
            print("\033[31mUsername already taken. Please try a different one.\033[0m")
            return None

        password = input("Choose a password: ").strip()
        if len(password) < 4:
            print("\033[31mPassword must be at least 4 characters.\033[0m")
            return None

        confirm = input("Confirm password: ").strip()
        if password != confirm:
            print("\033[31mPasswords do not match.\033[0m")
            return None

        pw_hash = self._hash_password(password)
        if db.create_user(username, pw_hash):
            row = db.get_user(username)
            print(f"\033[32m✔ Account created! Welcome, {username}!\033[0m")
            return {"id": row[0], "username": row[1]}
        else:
            print("\033[31mRegistration failed.\033[0m")
            return None

    def login(self, db: Database) -> dict | None:
        """Prompt for credentials. Returns user dict or None."""
        print("\n\033[32m─── LOGIN ───\033[0m")
        username = input("Username: ").strip()
        password = input("Password: ").strip()

        row = db.get_user(username)
        if row is None:
            print("\033[31mUser not found.\033[0m")
            return None

        pw_hash = self._hash_password(password)
        if pw_hash != row[2]:
            print("\033[31mIncorrect password.\033[0m")
            return None

        print(f"\033[32m✔ Welcome back, {username}!\033[0m")
        return {"id": row[0], "username": row[1]}


# ── Login screen ─────────────────────────────────────────────────────────────
def login_screen(db: Database) -> dict:
    """Show login/register screen. Loops until successful. Returns user dict."""
    auth = UserAuth()
    while True:
        print("\n\033[32m╔══════════════════════╗\033[0m")
        print("\033[32m║ Welcome to PennyPath ║\033[0m")
        print("\033[32m╚══════════════════════╝\033[0m")
        print("1. Login")
        print("2. Register")
        print("0. Quit")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            user = auth.login(db)
            if user:
                return user
        elif choice == "2":
            user = auth.register(db)
            if user:
                return user
        elif choice == "0":
            print("Goodbye!")
            exit(0)
        else:
            print("\033[31mInvalid option.\033[0m")


class WageAccount:
    def __init__(self):
        self.balance = 0

    def deposit_wage(self, amount):
        self.balance += amount
        print(amount, "has been deposited into the Wage Account.")
        print("Current wage account balance: ", self.balance)

    def withdraw_wage(self, amount, savings_account):
        if amount > self.balance:
            print("\033[31mInsufficient funds in wage account\033[0m")
        else:
            self.balance -= amount
            savings_account.balance += amount
            print(amount, "has been transfered to Savings Account")
            print("\033[32Remaining Wage Balance:\033[0m ", self.balance)




class Wages:
    def __init__(self):
        self.weekly_wage = 0


    def set_wage(self):
        print("\033[32mSet Weekly Wage\033[0m")
        print("---------------")
        self.weekly_wage = float(input("Set Weekly Wage: "))
        print("\033[32mWeekly wage as been set to:\033[0m", self.weekly_wage)


    def deposit_wage(self, wage_account, weeks=1):
        for week in range(1, weeks +1):
            wage_account.deposit_wage(self.weekly_wage)


    def wage_menu(self,wage_account, savings_account):

        while True:
            print("\033[32mWages Menu\033[0m")
            print("----------")
            print("1. Set Weekly Wage")
            print("2. Deposit to Wage Account")
            print("3. Transfer Wages to Savings")
            print("0. Exit")
            option = input("Choose an option: ")

            if option =="1":
                self.set_wage()

            elif option =="2":
                if self.weekly_wage <=0:
                    print("\033[31mPlease set weekly wage before depositing.\033[0m")
                else:
                    weeks=int(input("Enter number of weeks to deposit wages: "))
                    if weeks > 0:
                        self.deposit_wage(wage_account, weeks)
                    else:
                        print("\033[31mNumber of weeks must be greater than zero.\033[0m")
            elif option =="3":
                transfer_amount = float(input("Enter amount to transfer to savings: "))
                wage_account.withdraw_wage(transfer_amount, savings_account)

            elif option =="0":
                print("Exiting Wages Menu.")
                break
            else:
                print("\033[31mInvalid option\033[0m")







class Needs:
    SUBCATEGORIES = [
        "groceries", "rent/mortgage", "utilities", "gas/transport",
        "insurance", "bills", "healthcare", "childcare", "other"
    ]

    def __init__(self):
        self.name = input("What is the name of the expense? ").strip()
        self.ammt = float(input("How much is the expense? "))
        self.freq = input("How often is the charge? (Monthly, Weekly, Biweekly, or One Time): ").strip()
        self.subcategory = self._pick_subcategory()
        self.frm = ""

    @classmethod
    def _pick_subcategory(cls):
        print("\n  Sub-categories (Needs):")
        for i, s in enumerate(cls.SUBCATEGORIES, 1):
            print(f"    {i}. {s.title()}")
        while True:
            pick = input("  Choose sub-category number: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(cls.SUBCATEGORIES):
                return cls.SUBCATEGORIES[int(pick) - 1]
            print("\033[31m  Invalid choice, try again.\033[0m")

    def monthly_amount(self):
        if self.freq.lower() == "monthly":
            return self.ammt
        elif self.freq.lower() == "weekly":
            return self.ammt * 4
        elif self.freq.lower() == "biweekly":
            return self.ammt * 2
        elif self.freq.lower() == "one time":
            return self.ammt
        else:
            print("\033[31mInvalid frequency. Assuming monthly.\033[0m")
            return self.ammt

    def view_expense(self):
        print("Necessary")
        print("Name:", self.name)
        print("Sub-category:", self.subcategory.title())
        print("Amount: $", self.ammt)
        print("Frequency:", self.freq)
        print("Monthly Equivalent: $", self.monthly_amount())

class Wants:
    SUBCATEGORIES = [
        "dining out", "entertainment", "shopping", "subscriptions",
        "hobbies", "travel", "personal care", "gifts", "other"
    ]

    def __init__(self):
        self.name = input("What is the name of the expense? ").strip()
        self.ammt = float(input("How much is the expense? "))
        self.freq = input("How often is the charge? (Monthly, Weekly, Biweekly, or One Time): ").strip()
        self.subcategory = self._pick_subcategory()
        self.frm = ""

    @classmethod
    def _pick_subcategory(cls):
        print("\n  Sub-categories (Wants):")
        for i, s in enumerate(cls.SUBCATEGORIES, 1):
            print(f"    {i}. {s.title()}")
        while True:
            pick = input("  Choose sub-category number: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= len(cls.SUBCATEGORIES):
                return cls.SUBCATEGORIES[int(pick) - 1]
            print("\033[31m  Invalid choice, try again.\033[0m")

    def monthly_amount(self):
        if self.freq.lower() == "monthly":
            return self.ammt
        elif self.freq.lower() == "weekly":
            return self.ammt * 4
        elif self.freq.lower() == "biweekly":
            return self.ammt * 2
        elif self.freq.lower() == "one time":
            return self.ammt
        else:
            print("\033[31mInvalid frequency. Assuming monthly.\033[0m")
            return self.ammt

    def view_expense(self):
        print("Non-Necessary")
        print("Name:", self.name)
        print("Sub-category:", self.subcategory.title())
        print("Amount: $", self.ammt)
        print("Frequency:", self.freq)
        print("Monthly Equivalent: $", self.monthly_amount())

class Affordability:
    def __init__(self):
        self.max_allowable_payment = ""
        self.monthly_payment = ""
        self.inc = ""
        self.ammt = ""
        self.yint = ""
        self.mnth = ""
        self.intrt = ""

    def check_affordability(self):
        self.inc = int(input("What is your income?"))
        self.ammt = int(input("how much money is the item"))
        self.yint = int(input("What is the annual interest rate?"))
        self.mnth = int(input("How many Months is the loan?"))
        self.intrt = self.yint / 100 / 12
        if self.intrt > 0:
            self.monthly_payment = self.ammt * (self.intrt * (1 + self.intrt) ** self.mnth) / (
                    (1 + self.intrt) ** self.mnth - 1)
        else:
            self.monthly_payment = self.ammt / self.mnth
        self.max_allowable_payment = self.inc * .36
        if self.monthly_payment <= self.max_allowable_payment:
            print(f"\033[32mYou can afford the loan. Your monthly payment will be ${self.monthly_payment:.2f}.\033[0m")
        else:
            print(
                f"\033[31mYou cannot afford the loan. Your monthly payment would be ${self.monthly_payment:.2f}, but the maximum allowable payment is ${self.max_allowable_payment:.2f}.\033[0m")

class Budget:
    def __init__(self, checking_balance):
        self.bd =0
    def add_budget(self):
        self.bd = int(input("Enter Wants Budget"))
    def display_budget(self):
        print("Current wants budget: ", self.bd)
    def modify(self, checking_balance):
        new_budget = int(input("Enter new budget: "))
        while new_budget > checking_balance:
            print("New budget cannot exceed checking balance.")
            new_budget = int(input("Enter new budget: "))
        self.bd = new_budget



def view_totals(necessary_total, nonnecessary_total, checking_account):
    total_expenses = necessary_total + nonnecessary_total
    remaining_balance = checking_account.balance - total_expenses
    checking_account.balance = remaining_balance

    print("\033[32m--- Expense Totals ---\033[0m")
    print(f"Total Necessary Expenses: ${necessary_total:.2f}")
    print(f"Total Non-Necessary Expenses: ${nonnecessary_total:.2f}")
    print(f"Overall Monthly Expenses: ${total_expenses:.2f}")
    print(f"Remaining Checking Balance: ${checking_account.balance:.2f}")
    if remaining_balance < 0:
        print("\033[31mWarning: Your expenses exceed your checking balance\033[0m")
    else:
        print("\033[32mYou are within your budget.\033[0m")


class Account:
    def __init__(self, balance=0):
        self.balance = balance

    def add_balance(self, amount):
        amount = float(input("Add to your account: "))
        self.balance += amount
        print("__________________________")
        print("\033[32mNew Account Balance:\033[0m ", self.balance)
        print("__________________________")

    def deduct_balance(self, amount):
        if amount > self.balance:
            print("__________________________")
            print("\033[31mInsufficient account fund\033[0m")
            print("__________________________")

        else:
            self.balance -= amount
            print("__________________________")
            print("\033[32mNew savings balance:\033[0m", self.balance)
            print("__________________________")

    def transfer(self, amount, target_account):
        if amount > self.balance:
            print("\033[31mInsufficient funds for transfer\033[0m")
        else:
            self.balance -= amount
            target_account.balance += amount
            print("-------------------")
            print("Transfer Successful")
            print("-------------------")


class SavingsAccount(Account):
    def __init__(self, balance=0):
        super().__init__(balance)

    def remove_savings(self):
            print("Savings Balance rest to $0.00")
            self.balance = 0
    def add_savings(self, amount):
        self.balance += amount


    def savings_menu(self, checking_account):
        while True:
            print("\033[32mSAVINGS MENU\033[0m")
            print("Current Savings: ", self.balance)
            print("1. Add Savings")
            print("2. Remove Savings")
            print("3. Deduct")
            print("4. Transfer")
            print("5. Exit")

            option = input("Please choose an option: ")

            if option == "1":
                amount = float(input("How much would you like to add: "))
                self.add_savings(amount)
            elif option == "2":
                self.remove_savings()
            elif option =="3":
                amount = float(input("How much would you like to deduct: "))
                self.deduct_balance(amount)
            elif option =="4":
                amount = float(input("How much would you like to transfer to checking?: "))
                self.transfer(amount, checking_account)
            elif option == "5":
                break
            else:
                print("\033[31mInvalid option\033[0m")

class CheckingAccount(Account):
    def __init__(self, balance=0):
        super().__init__(balance)

    def remove_checking(self):
        self.balance = 0
        print("Checking balance reset to $0.00")
    def checking_menu(self, savings_account):

        while True:

            print("\033[32mCHECKING MENU\033[0m")
            print("Current Checking: ", self.balance)
            print("1. Add to Checking")
            print("2. Remove Checking")
            print("3. Deduct")
            print("4. Transfer")
            print("5. Exit")

            option = input("Please choose an option: ")

            if option == "1":
                amount = float(input("Enter amount to add to checking: "))
                self.add_balance(amount)
            elif option == "2":
                self.remove_checking()
            elif option == "3":
                amount = float(input("Enter amount to deduct from checking: "))
                self.deduct_balance(amount)
            elif option == "4":
                amount = float(input("How much would you like to transfer to savings?: "))
                self.transfer(amount, savings_account)
            elif option == "5":
                break
            else:
                print("\033[31mInvalid Option\033[0m")



class BudgetAdvisor:
    """
    ML-powered budget recommendation engine.

    Trains one LinearRegression model per spending sub-category using
    benchmark ratios derived from BLS Consumer Expenditure Survey data.
    Recommendations are then personalised with a 70/30 blend of the
    baseline targets and the user's own spending ratios.
    """

    # ── Sub-category benchmark ratios (% of monthly income) ──────────────
    # Needs sub-categories  (target total ≈ 50 %)
    NEEDS_BENCHMARKS = {
        "groceries":      0.10,
        "rent/mortgage":  0.28,
        "utilities":      0.05,
        "gas/transport":  0.06,
        "insurance":      0.05,
        "bills":          0.04,
        "healthcare":     0.03,
        "childcare":      0.04,
        "other":          0.02,   # catch-all needs
    }
    # Wants sub-categories (target total ≈ 30 %)
    WANTS_BENCHMARKS = {
        "dining out":    0.05,
        "entertainment": 0.04,
        "shopping":      0.06,
        "subscriptions": 0.02,
        "hobbies":       0.03,
        "travel":        0.03,
        "personal care": 0.03,
        "gifts":         0.02,
        "other":         0.02,   # catch-all wants
    }

    # Top-level 50/30/20 ratios
    NEEDS_RATIO   = 0.50
    WANTS_RATIO   = 0.30
    SAVINGS_RATIO = 0.20

    # Training income anchor points ($500 – $15,000/mo)
    _INCOMES = np.array([500, 1000, 2000, 3000, 4000,
                         5000, 6000, 8000, 10000, 15000]).reshape(-1, 1)

    def __init__(self):
        # Top-level models
        self.needs_model   = LinearRegression()
        self.wants_model   = LinearRegression()
        self.savings_model = LinearRegression()
        # Per-subcategory models  {subcategory: LinearRegression}
        self.sub_models: dict = {}
        self._trained = False

    # ------------------------------------------------------------------ #
    #  Training                                                            #
    # ------------------------------------------------------------------ #
    def train(self):
        """Fit top-level and per-subcategory linear models."""
        X = self._INCOMES
        inc = X.flatten()

        # Top-level
        self.needs_model.fit(X,   inc * self.NEEDS_RATIO)
        self.wants_model.fit(X,   inc * self.WANTS_RATIO)
        self.savings_model.fit(X, inc * self.SAVINGS_RATIO)

        # Per-subcategory
        all_benchmarks = {**self.NEEDS_BENCHMARKS, **self.WANTS_BENCHMARKS}
        for sub, ratio in all_benchmarks.items():
            model = LinearRegression()
            model.fit(X, inc * ratio)
            self.sub_models[sub] = model

        self._trained = True

    # ------------------------------------------------------------------ #
    #  Recommendation                                                      #
    # ------------------------------------------------------------------ #
    def recommend(self, monthly_income: float,
                  actual_needs: float, actual_wants: float,
                  expenses: list | None = None) -> dict | None:
        """
        Returns a recommendation dict.
        expenses – list of Needs/Wants objects (used for subcategory breakdown).
        """
        if not self._trained:
            self.train()
        if monthly_income <= 0:
            return None

        X = np.array([[monthly_income]])

        # Top-level ML baseline
        base_needs   = float(self.needs_model.predict(X)[0])
        base_wants   = float(self.wants_model.predict(X)[0])
        base_savings = float(self.savings_model.predict(X)[0])

        # Personalised blend (only needs & wants are blended with user behaviour;
        # savings is derived as the remainder so the three always sum to 100 %)
        actual_needs_ratio = actual_needs / monthly_income
        actual_wants_ratio = actual_wants / monthly_income

        blended_needs   = 0.70 * base_needs + 0.30 * actual_needs_ratio * monthly_income
        blended_wants   = 0.70 * base_wants + 0.30 * actual_wants_ratio * monthly_income
        blended_savings = monthly_income - blended_needs - blended_wants

        # ── Sub-category breakdown ─────────────────────────────────────
        sub_actual: dict = {}   # {subcategory: monthly_amount}
        if expenses:
            for exp in expenses:
                sub = getattr(exp, "subcategory", "other")
                sub_actual[sub] = sub_actual.get(sub, 0.0) + exp.monthly_amount()

        sub_recommendations: dict = {}
        all_benchmarks = {**self.NEEDS_BENCHMARKS, **self.WANTS_BENCHMARKS}
        for sub, model in self.sub_models.items():
            base_sub   = float(model.predict(X)[0])
            actual_sub = sub_actual.get(sub, 0.0)
            actual_sub_ratio = actual_sub / monthly_income
            # Blend: if user has data for this sub, personalise; else pure baseline
            if actual_sub > 0:
                blended_sub = 0.70 * base_sub + 0.30 * actual_sub_ratio * monthly_income
            else:
                blended_sub = base_sub
            sub_recommendations[sub] = {
                "recommended": blended_sub,
                "actual":      actual_sub,
                "benchmark_ratio": all_benchmarks[sub],
            }

        return {
            "monthly_income": monthly_income,
            "rec_needs":      blended_needs,
            "rec_wants":      blended_wants,
            "rec_savings":    blended_savings,
            "actual_needs":   actual_needs,
            "actual_wants":   actual_wants,
            "actual_savings": monthly_income - actual_needs - actual_wants,
            "base_needs":     base_needs,
            "base_wants":     base_wants,
            "base_savings":   base_savings,
            "subcategories":  sub_recommendations,
        }

    # ------------------------------------------------------------------ #
    #  Tips per subcategory                                                #
    # ------------------------------------------------------------------ #
    _TIPS = {
        "groceries":     "Try meal-prepping and shopping with a list to cut grocery costs.",
        "rent/mortgage": "Consider refinancing or finding a roommate to reduce housing costs.",
        "utilities":     "Unplug devices when not in use and check for better energy plans.",
        "gas/transport": "Combine errands, carpool, or use public transit to cut fuel costs.",
        "insurance":     "Shop around annually — bundling policies often saves 10–25 %.",
        "bills":         "Call providers to negotiate rates or switch to lower-cost plans.",
        "healthcare":    "Use generic medications and preventive care to reduce costs.",
        "childcare":     "Look into dependent care FSAs or local subsidy programmes.",
        "dining out":    "Cook at home 1–2 more nights per week to trim dining costs.",
        "entertainment": "Look for free local events, libraries, and streaming bundles.",
        "shopping":      "Use a 24-hour rule before non-essential purchases.",
        "subscriptions": "Audit your subscriptions — cancel anything unused for 30+ days.",
        "hobbies":       "Borrow gear from libraries or buy second-hand equipment.",
        "travel":        "Book 6–8 weeks ahead and use points/miles to offset costs.",
        "personal care": "DIY routines and drugstore brands rival salon products.",
        "gifts":         "Set annual gift budgets per person and shop sales/off-season.",
        "other":         "Track miscellaneous spending for a month to find hidden leaks.",
    }

    # ------------------------------------------------------------------ #
    #  Report                                                              #
    # ------------------------------------------------------------------ #
    def display_report(self, monthly_income: float,
                       actual_needs: float, actual_wants: float,
                       expenses: list | None = None):
        """Print a detailed, subcategory-level budget report."""
        if monthly_income <= 0:
            print("\033[31mCannot generate report: monthly income is $0.00.\033[0m")
            print("Please set your weekly wage in the Wages menu first.")
            return

        r = self.recommend(monthly_income, actual_needs, actual_wants, expenses)
        if r is None:
            return

        sep  = "=" * 58
        thin = "-" * 58

        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   💡  BUDGET RECOMMENDATION REPORT\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print(f"  Monthly Income   : \033[33m${r['monthly_income']:>10.2f}\033[0m")
        print(thin)

        # ── Top-level summary ─────────────────────────────────────────
        print(f"  {'Category':<20} {'Recommended':>12}  {'Actual':>10}")
        print(thin)

        def _color(actual, rec, higher_is_bad=True):
            if higher_is_bad:
                return "\033[31m" if actual > rec else "\033[32m"
            return "\033[31m" if actual < rec else "\033[32m"

        nc = _color(r['actual_needs'],   r['rec_needs'])
        wc = _color(r['actual_wants'],   r['rec_wants'])
        sc = _color(r['actual_savings'], r['rec_savings'], higher_is_bad=False)

        print(f"  {'Needs (50%)':<20} ${r['rec_needs']:>10.2f}  "
              f"{nc}${r['actual_needs']:>9.2f}\033[0m")
        print(f"  {'Wants (30%)':<20} ${r['rec_wants']:>10.2f}  "
              f"{wc}${r['actual_wants']:>9.2f}\033[0m")
        print(f"  {'Savings (20%)':<20} ${r['rec_savings']:>10.2f}  "
              f"{sc}${r['actual_savings']:>9.2f}\033[0m")
        print(thin)

        # ── Subcategory breakdown ─────────────────────────────────────
        subs = r["subcategories"]
        has_any = any(v["actual"] > 0 for v in subs.values())

        if has_any:
            print("\033[33m  📊  Subcategory Breakdown:\033[0m")
            print(f"  {'Subcategory':<22} {'Benchmark %':>11}  {'Recommended':>12}  {'Actual':>10}")
            print(thin)

            needs_subs = list(self.NEEDS_BENCHMARKS.keys())
            wants_subs = list(self.WANTS_BENCHMARKS.keys())

            def _print_group(label, sub_keys):
                print(f"  \033[36m── {label} ──\033[0m")
                for sub in sub_keys:
                    info = subs[sub]
                    if info["actual"] == 0 and info["recommended"] == info["recommended"]:
                        # Skip untracked zero-actual subs unless user has something there
                        pass
                    pct  = f"{info['benchmark_ratio']*100:.0f}%"
                    rec  = info["recommended"]
                    act  = info["actual"]
                    color = _color(act, rec) if act > 0 else "\033[90m"
                    act_str = f"{color}${act:>9.2f}\033[0m" if act > 0 else "\033[90m       ---\033[0m"
                    print(f"  {sub.title():<22} {pct:>11}  ${rec:>10.2f}  {act_str}")

            _print_group("NEEDS", needs_subs)
            _print_group("WANTS", wants_subs)
            print(thin)

        # ── Insights & tips ───────────────────────────────────────────
        print("\033[33m  💬  Insights:\033[0m")
        insights_shown = False

        # Top-level checks
        if r['actual_needs'] > r['rec_needs']:
            over = r['actual_needs'] - r['rec_needs']
            print(f"  ⚠  Needs are \033[31m${over:.2f} over\033[0m the recommended limit.")
            insights_shown = True

        if r['actual_wants'] > r['rec_wants']:
            over = r['actual_wants'] - r['rec_wants']
            print(f"  ⚠  Wants are \033[31m${over:.2f} over\033[0m the recommended limit.")
            insights_shown = True

        if r['actual_savings'] < r['rec_savings']:
            under = r['rec_savings'] - r['actual_savings']
            print(f"  ⚠  Savings are \033[31m${under:.2f} below\033[0m the recommended target.")
            print("     Tip: Automate a small recurring transfer to your savings account.")
            insights_shown = True

        # Per-subcategory tips for overspent categories
        for sub, info in subs.items():
            if info["actual"] > 0 and info["actual"] > info["recommended"]:
                over = info["actual"] - info["recommended"]
                tip  = self._TIPS.get(sub, "")
                print(f"  ⚠  \033[33m{sub.title()}\033[0m is "
                      f"\033[31m${over:.2f} over\033[0m its target.")
                if tip:
                    print(f"     💡 {tip}")
                insights_shown = True

        if not insights_shown:
            print("  ✅  Great job! Spending is within all recommended limits.")
            print("     Consider investing your surplus for long-term growth.")

        # ── Baseline targets footer ───────────────────────────────────
        print(thin)
        print("\033[33m  50/30/20 Baseline Targets:\033[0m")
        print(f"    Needs   → ${r['base_needs']:.2f}")
        print(f"    Wants   → ${r['base_wants']:.2f}")
        print(f"    Savings → ${r['base_savings']:.2f}")
        print("\033[32m" + sep + "\033[0m")
        print()


# ── Home Savings Plan ─────────────────────────────────────────────────────────
class HomeSavingsPlan:
    """
    Uses FRED median home-price data (fredgraph.csv) to predict future home
    prices via LinearRegression and KNeighborsRegressor, then builds a
    personalised monthly savings plan so the user can afford a down payment
    by a chosen target year.

    Regions in the CSV:
        MSPUS  – United States (national)
        MSPNE  – Northeast
        MSPMW  – Midwest
        MSPS   – South
        MSPW   – West
    """

    CSV_FILE = "fredgraph.csv"

    REGION_LABELS = {
        "1": ("MSPUS", "United States (National)"),
        "2": ("MSPNE", "Northeast"),
        "3": ("MSPMW", "Midwest"),
        "4": ("MSPS",  "South"),
        "5": ("MSPW",  "West"),
    }

    DOWN_PAYMENT_PCTS = {
        "1": (0.03,  "3%  – Conventional minimum (with PMI)"),
        "2": (0.05,  "5%  – Low down payment"),
        "3": (0.10,  "10% – Moderate down payment"),
        "4": (0.20,  "20% – Avoid PMI (recommended)"),
        "5": (0.25,  "25% – Strong equity position"),
    }

    def __init__(self):
        self._df        = None
        self._lr_models  = {}   # {col: LinearRegression}
        self._knn_models = {}   # {col: KNeighborsRegressor}
        self._trained    = False
        self._load_and_train()

    # ── Data & Training ───────────────────────────────────────────────
    def _load_and_train(self):
        """Load CSV and train LR + KNN models for every region column."""
        if not os.path.exists(self.CSV_FILE):
            print(f"\033[31m  [HomeSavingsPlan] '{self.CSV_FILE}' not found — "
                  f"feature unavailable.\033[0m")
            return

        df = pd.read_csv(self.CSV_FILE)
        df['observation_date'] = pd.to_datetime(df['observation_date'])
        df['date_numeric'] = df['observation_date'].astype(np.int64) / 10**9
        self._df = df

        cols = ['MSPUS', 'MSPNE', 'MSPMW', 'MSPS', 'MSPW']
        X = df['date_numeric'].values.reshape(-1, 1)
        y_all = df[cols]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_all, test_size=0.2, random_state=42
        )

        for col in cols:
            lr = LinearRegression()
            lr.fit(X_train, y_train[col])
            self._lr_models[col] = lr

            knn = KNeighborsRegressor(n_neighbors=3)
            knn.fit(X_train, y_train[col])
            self._knn_models[col] = knn

        self._trained = True

        # Print model accuracy on hold-out set

    # ── Prediction helpers ────────────────────────────────────────────
    def _date_to_numeric(self, year: int, quarter: int = 1) -> float:
        """Convert a year + quarter (1-4) to Unix timestamp (seconds),
        matching the scale used during training (nanoseconds / 10**9)."""
        month = (quarter - 1) * 3 + 1
        ts = pd.Timestamp(year=year, month=month, day=1)
        return float(ts.value) / 10**9

    def _predict_price(self, col: str, year: int) -> dict:
        """Return LR and KNN predicted prices for a given region and year.

        LR is capped at a 4 % annual appreciation from the most recent
        actual price so straight-line extrapolation never goes wildly off.
        KNN is naturally bounded because it averages real neighbours.
        """
        x = np.array([[self._date_to_numeric(year)]])

        latest_price = float(self._df[col].iloc[-1])
        latest_year  = self._df['observation_date'].iloc[-1].year
        years_ahead  = max(0, year - latest_year)
        # 4 % p.a. compound cap
        price_cap    = latest_price * (1.04 ** years_ahead)

        lr_raw  = float(self._lr_models[col].predict(x)[0])
        knn_raw = float(self._knn_models[col].predict(x)[0])

        return {
            "lr":  max(latest_price, min(lr_raw,  price_cap)),
            "knn": max(latest_price, min(knn_raw, price_cap)),
        }

    # ── Savings plan calculator ───────────────────────────────────────
    @staticmethod
    def _savings_plan(target_price: float, down_pct: float,
                      current_savings: float, months_remaining: int) -> dict:
        down_payment_needed = target_price * down_pct
        still_needed        = max(0.0, down_payment_needed - current_savings)
        monthly_needed      = still_needed / months_remaining if months_remaining > 0 else still_needed
        return {
            "down_payment":   down_payment_needed,
            "already_saved":  current_savings,
            "still_needed":   still_needed,
            "monthly_needed": monthly_needed,
        }

    # ── Chart ─────────────────────────────────────────────────────────
    def _show_chart(self, col: str, region_name: str,
                    target_year: int, predicted_lr: float, predicted_knn: float,
                    savings_balance: float, down_pct: float):
        """Plot historical prices + LR & KNN forecast lines + down-payment goal."""
        df = self._df
        X_hist = df['date_numeric'].values.reshape(-1, 1)

        # Build a future date range from last data point → target year Q1
        last_ts  = df['date_numeric'].max()
        fut_ts   = self._date_to_numeric(target_year)
        fut_x    = np.linspace(last_ts, fut_ts, 20).reshape(-1, 1)
        fut_dates = pd.to_datetime(fut_x.flatten(), unit='s')

        lr_fut  = self._lr_models[col].predict(fut_x)
        knn_fut = self._knn_models[col].predict(fut_x)

        fig, ax = plt.subplots(figsize=(13, 6))

        # Historical scatter
        ax.scatter(df['observation_date'], df[col],
                   color='steelblue', s=14, alpha=0.7, label='Historical (FRED)')

        # LR full fit line over history
        lr_hist = self._lr_models[col].predict(X_hist)
        ax.plot(df['observation_date'], lr_hist,
                color='tomato', linewidth=1.2, linestyle='--', label='LR fit (historical)')

        # Forecast lines
        ax.plot(fut_dates, lr_fut,
                color='tomato', linewidth=2, linestyle='-', label='LR forecast')
        ax.plot(fut_dates, knn_fut,
                color='darkorange', linewidth=2, linestyle='-', label='KNN forecast')

        # Down-payment target lines
        goal_lr  = predicted_lr  * down_pct
        goal_knn = predicted_knn * down_pct
        ax.axhline(predicted_lr,  color='tomato',    linestyle=':', alpha=0.7,
                   label=f'LR target price  ${predicted_lr:,.0f}')
        ax.axhline(predicted_knn, color='darkorange', linestyle=':', alpha=0.7,
                   label=f'KNN target price ${predicted_knn:,.0f}')
        ax.axhline(savings_balance, color='limegreen', linewidth=1.5, linestyle='-.',
                   label=f'Current savings  ${savings_balance:,.0f}')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        plt.xticks(rotation=45)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'${v:,.0f}')
        )
        ax.set_xlabel('Year')
        ax.set_ylabel('Median Home Price (USD)')
        ax.set_title(f'Home Price Forecast – {region_name}\n'
                     f'Target: {target_year}  |  Down payment: {down_pct*100:.0f}%')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    # ── Public entry point ────────────────────────────────────────────
    def run(self, savings_balance: float, monthly_income: float):
        """Interactive home-savings planning session."""
        if not self._trained:
            print("\033[31m  Home savings plan unavailable (CSV not loaded).\033[0m")
            return

        sep  = "=" * 60
        thin = "-" * 60
        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   🏠  HOME SAVINGS PLAN\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print("  Uses FRED median home-price data + ML to forecast prices")
        print("  and calculate how much you need to save each month.")
        print(thin)

        # ── Step 1: Region ────────────────────────────────────────────
        print("\n  Select your target region:")
        for k, (col, label) in self.REGION_LABELS.items():
            print(f"    {k}. {label}")
        while True:
            pick = input("  Region (1-5): ").strip()
            if pick in self.REGION_LABELS:
                col, region_name = self.REGION_LABELS[pick]
                break
            print("\033[31m  Invalid choice.\033[0m")

        # ── Step 2: Target year ───────────────────────────────────────
        today        = datetime.date.today()
        current_year = today.year
        current_month = today.month
        while True:
            try:
                target_year = int(input(f"  Target purchase year (e.g. {current_year + 5}): ").strip())
                if target_year < current_year:
                    print(f"\033[31m  Must be {current_year} or later.\033[0m")
                    continue
                break
            except ValueError:
                print("\033[31m  Enter a valid year.\033[0m")

        # ── Step 3: Down payment % ────────────────────────────────────
        print("\n  Select down-payment percentage:")
        for k, (pct, label) in self.DOWN_PAYMENT_PCTS.items():
            print(f"    {k}. {label}")
        while True:
            pick = input("  Choice (1-5): ").strip()
            if pick in self.DOWN_PAYMENT_PCTS:
                down_pct, dp_label = self.DOWN_PAYMENT_PCTS[pick]
                break
            print("\033[31m  Invalid choice.\033[0m")

        # ── Step 4: Current savings override ─────────────────────────
        print(f"\n  Your current savings account balance: \033[33m${savings_balance:,.2f}\033[0m")
        override = input("  Use this amount as your starting savings? (yes/no): ").strip().lower()
        if override != "yes":
            while True:
                try:
                    savings_balance = float(input("  Enter current home-savings amount: $").strip())
                    break
                except ValueError:
                    print("\033[31m  Enter a valid number.\033[0m")

        # ── Step 5: Predict & calculate ───────────────────────────────
        prices     = self._predict_price(col, target_year)
        lr_price   = prices["lr"]
        knn_price  = prices["knn"]
        avg_price  = (lr_price + knn_price) / 2

        months_remaining = max(1, (target_year - current_year) * 12 + (1 - current_month))

        lr_plan  = self._savings_plan(lr_price,  down_pct, savings_balance, months_remaining)
        knn_plan = self._savings_plan(knn_price, down_pct, savings_balance, months_remaining)
        avg_plan = self._savings_plan(avg_price, down_pct, savings_balance, months_remaining)

        # Most recent actual price
        last_row   = self._df.iloc[-1]
        latest_price = last_row[col]
        latest_date  = last_row['observation_date'].strftime('%Y-%m')

        # ── Report ────────────────────────────────────────────────────
        print()
        print("\033[32m" + sep + "\033[0m")
        print(f"  Region   : \033[33m{region_name}\033[0m")
        print(f"  Latest price ({latest_date}): \033[33m${latest_price:,.0f}\033[0m")
        print(f"  Target year : \033[33m{target_year}\033[0m  "
              f"({months_remaining} months away)")
        print(f"  Down payment: \033[33m{dp_label}\033[0m")
        print(thin)
        print(f"  {'Model':<10} {'Predicted Price':>16}  {'Down Payment':>13}  "
              f"{'Monthly Savings':>16}")
        print(thin)

        for label, price, plan in [
            ("LR",      lr_price,  lr_plan),
            ("KNN",     knn_price, knn_plan),
            ("Average", avg_price, avg_plan),
        ]:
            feasible = plan["monthly_needed"] <= monthly_income * 0.20
            color    = "\033[32m" if feasible else "\033[31m"
            print(f"  {label:<10} ${price:>14,.0f}  "
                  f"${plan['down_payment']:>12,.0f}  "
                  f"{color}${plan['monthly_needed']:>14,.2f}\033[0m")

        print(thin)
        print(f"  Current savings : \033[33m${savings_balance:,.2f}\033[0m")
        print(f"  Still needed    : \033[33m${avg_plan['still_needed']:,.2f}\033[0m  "
              f"(based on avg model)")
        print(thin)

        # Affordability check against income
        rec_monthly = avg_plan["monthly_needed"]
        max_save    = monthly_income * 0.20   # 20 % rule
        print("\033[33m  💬  Insights:\033[0m")
        if monthly_income <= 0:
            print("  ⚠  Set your weekly wage first to see income-based insights.")
        elif rec_monthly <= 0:
            print("  ✅  You already have enough saved for the down payment!")
        elif rec_monthly <= max_save:
            print(f"  ✅  Saving \033[32m${rec_monthly:,.2f}/mo\033[0m fits within your "
                  f"recommended 20% savings budget (${max_save:,.2f}/mo).")
        else:
            gap = rec_monthly - max_save
            print(f"  ⚠  You need \033[31m${rec_monthly:,.2f}/mo\033[0m but your 20% "
                  f"savings budget is only ${max_save:,.2f}/mo.")
            print(f"     To stay on track, consider extending your timeline by "
                  f"~{int(gap / (max_save / months_remaining) + months_remaining) - months_remaining} months,")
            print(f"     increasing income, or reducing expenses by \033[31m${gap:,.2f}/mo\033[0m.")

        print("\033[32m" + sep + "\033[0m")

        # ── Optional chart ────────────────────────────────────────────
        show = input("\n  Show price forecast chart? (yes/no): ").strip().lower()
        if show == "yes":
            self._show_chart(col, region_name, target_year,
                             lr_price, knn_price, savings_balance, down_pct)


def main_menu(username: str):
    print(f"\n\033[32mMAIN MENU\033[0m  \033[33m[{username}]\033[0m")
    print("1. Savings")
    print("2. Checking")
    print("3. Affordability")
    print("4. Wage")
    print("5. Tips")
    print("6. Logout")
    print("7. Exit")
    return input("Please choose an option: ")


def print_delay(text, delay=0.1):
    for letter in text:
        print(letter, end='', flush=True)
        time.sleep(delay)


# ── Main entry point ─────────────────────────────────────────────────────────
def general_program():
    db = Database()

    # ── Login gate ────────────────────────────────────────────────────────
    current_user = login_screen(db)   # {"id": int, "username": str}
    user_id      = current_user["id"]
    username     = current_user["username"]

    def load_user_session():
        """Load fresh account objects for the logged-in user."""
        nonlocal savings_account, checking_account, wages, b
        nonlocal expenses, necessary_total, nonnecessary_total

        session = db.load_session(user_id)
        savings_account.balance  = session["savings"]
        checking_account.balance = session["checking"]
        wages.weekly_wage        = session["wage"]
        expenses.clear()
        necessary_total    = 0.0
        nonnecessary_total = 0.0

        for cat, sub, name, amount, freq in session["expenses"]:
            obj = object.__new__(Needs if cat == "needs" else Wants)
            obj.name = name
            obj.ammt = amount
            obj.freq = freq
            obj.frm  = ""
            obj.subcategory = sub
            expenses.append(obj)
            if cat == "needs":
                necessary_total    += obj.monthly_amount()
            else:
                nonnecessary_total += obj.monthly_amount()

        b = None
        if session["budget"] > 0:
            b = Budget(checking_account.balance)
            b.bd = session["budget"]

    savings_account  = SavingsAccount()
    checking_account = CheckingAccount()
    wages            = Wages()
    expenses         = []
    necessary_total    = 0.0
    nonnecessary_total = 0.0
    b                = None

    load_user_session()

    if any([savings_account.balance, checking_account.balance, wages.weekly_wage]):
        print("\033[32m✔ Previous session restored.\033[0m")

    wage_account = WageAccount()
    advisor      = BudgetAdvisor()
    advisor.train()
    home_plan    = HomeSavingsPlan()

    def autosave():
        db.save_session(
            savings_account.balance,
            checking_account.balance,
            wages.weekly_wage,
            b.bd if b is not None else None,
            user_id
        )

    while True:
        print_delay("\033[32mWelcome to PennyPath\033[0m: ", .05)
        print_delay("Enter 1 to Continue", .0)
        option = input()

        if option == "1":
            while True:
                option = main_menu(username)

                if option == "1":
                    savings_account.savings_menu(checking_account)
                    autosave()

                elif option == "2":
                    checking_account.checking_menu(savings_account)
                    autosave()

                elif option == "3":
                    while True:
                        print("\033[32mAFFORDABILITY MENU\033[0m")
                        print("1.  Add Needs Expenses")
                        print("2.  Add Wants Expense")
                        print("3.  View Expenses")
                        print("4.  View Totals")
                        print("5.  Affordability")
                        print("6.  Set Budget")
                        print("7.  Modify Budget")
                        print("8.  Budget Advisor")
                        print("9.  Clear All Expenses")
                        print("10. Home Savings Plan")
                        print("11. Exit")
                        num = input("Enter choice: ")

                        if num == "1":
                            e = Needs()
                            expenses.append(e)
                            necessary_total += e.monthly_amount()
                            db.save_expense("needs", e.subcategory, e.name, e.ammt, e.freq, user_id)

                        elif num == "2":
                            ne = Wants()
                            expenses.append(ne)
                            nonnecessary_total += ne.monthly_amount()
                            db.save_expense("wants", ne.subcategory, ne.name, ne.ammt, ne.freq, user_id)

                        elif num == "3":
                            for x in expenses:
                                x.view_expense()

                        elif num == "4":
                            view_totals(necessary_total, nonnecessary_total, checking_account)
                            if b is not None:
                                bdleft = b.bd - nonnecessary_total
                                if nonnecessary_total >= b.bd:
                                    print("You have spent your monthly budget")
                                elif nonnecessary_total >= b.bd * .9:
                                    print("You have spent more than 90% of your budget")
                                print("Budget Left:", bdleft)
                            else:
                                print("\033[33mNo budget set. Use option 6.\033[0m")
                            autosave()

                        elif num == "5":
                            a = Affordability()
                            a.check_affordability()

                        elif num == "6":
                            b = Budget(checking_account.balance)
                            b.add_budget()
                            while b.bd > checking_account.balance:
                                print("Budget cannot exceed checking balance")
                                b.bd = int(input("Enter Wants Budget: "))
                            db.save_budget(b.bd, user_id)

                        elif num == "7":
                            if b is not None:
                                b.modify(checking_account.balance)
                                db.save_budget(b.bd, user_id)
                            else:
                                print("\033[31mNo budget set. Use option 6 first.\033[0m")

                        elif num == "8":
                            monthly_income = wages.weekly_wage * 4
                            advisor.display_report(monthly_income, necessary_total, nonnecessary_total, expenses)

                        elif num == "9":
                            confirm = input("Clear ALL saved expenses? (yes/no): ")
                            if confirm.lower() == "yes":
                                expenses.clear()
                                necessary_total    = 0.0
                                nonnecessary_total = 0.0
                                db.clear_expenses(user_id)
                                print("\033[32mAll expenses cleared.\033[0m")

                        elif num == "10":
                            monthly_income = wages.weekly_wage * 4
                            home_plan.run(savings_account.balance, monthly_income)

                        elif num == "11":
                            break
                        else:
                            print("Invalid choice.")

                elif option == "4":
                    wages.wage_menu(wage_account, savings_account)
                    autosave()

                elif option == "5":
                    pass  # tips menu

                elif option == "6":
                    # ── LOGOUT ────────────────────────────────────────
                    autosave()
                    print(f"\033[32m✔ Session saved. Logged out as {username}.\033[0m")

                    # Reset all account state
                    savings_account  = SavingsAccount()
                    checking_account = CheckingAccount()
                    wages            = Wages()
                    expenses         = []
                    necessary_total    = 0.0
                    nonnecessary_total = 0.0
                    b                = None

                    # Return to login screen
                    current_user = login_screen(db)
                    user_id      = current_user["id"]
                    username     = current_user["username"]
                    load_user_session()
                    if any([savings_account.balance, checking_account.balance,
                            wages.weekly_wage]):
                        print("\033[32m✔ Previous session restored.\033[0m")
                    break   # break inner loop → re-enter outer welcome loop

                elif option == "7":
                    autosave()
                    db.close()
                    print("\033[32m✔ Session saved. Goodbye!\033[0m")
                    return


general_program()
