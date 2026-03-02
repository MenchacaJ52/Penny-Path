import time
import hashlib
import os
from sklearn.linear_model import LinearRegression
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
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                category  TEXT NOT NULL,
                name      TEXT NOT NULL,
                amount    REAL NOT NULL,
                frequency TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS budget (
                user_id INTEGER PRIMARY KEY,
                amount  REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        self.conn.commit()

    # ── Users ─────────────────────────────────────────────────────────────
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
    def save_expense(self, category: str, name: str, amount: float,
                     frequency: str, user_id: int):
        self.conn.execute(
            "INSERT INTO expenses (user_id, category, name, amount, frequency) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, category, name, amount, frequency)
        )
        self.conn.commit()

    def load_expenses(self, user_id: int) -> list:
        return self.conn.execute(
            "SELECT category, name, amount, frequency FROM expenses WHERE user_id = ?",
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
    def __init__(self):
        self.name = input("What is the name of the Expense")
        self.ammt = float(input("How much is the expense"))
        self.freq = input("How often is the charge?(Monthly, Weekly,or Biweekly, or One Time")
        self.frm = ""

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
        print("Name:",self.name)
        print("Amount: $",self.ammt)
        print("Frequency:",self.freq)
        print("Monthly Equivalent: $", self.monthly_amount())

class Wants:
    def __init__(self):
        self.name = input("What is the name of the Expense")
        self.ammt = float(input("How much is the expense"))
        self.freq = input("How often is the charge?(Monthly, Weekly,or Biweekly, or One Time")
        self.frm = ""

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
        print("Name:",self.name)
        print("Amount: $",self.ammt)
        print("Frequency:",self.freq)
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
    Uses scikit-learn LinearRegression trained on 50/30/20 rule anchor points,
    then adjusts recommendations based on the user's actual spending ratios.
    """

    # 50/30/20 rule allocation ratios
    NEEDS_RATIO  = 0.50
    WANTS_RATIO  = 0.30
    SAVINGS_RATIO = 0.20

    def __init__(self):
        self.needs_model   = LinearRegression()
        self.wants_model   = LinearRegression()
        self.savings_model = LinearRegression()
        self._trained = False

    # ------------------------------------------------------------------ #
    #  Training                                                            #
    # ------------------------------------------------------------------ #
    def train(self):
        """
        Fit three tiny linear models on synthetic 50/30/20 anchor points.
        Incomes from $500/mo to $15,000/mo are used as training data.
        """
        incomes = np.array([500, 1000, 2000, 3000, 4000,
                            5000, 6000, 8000, 10000, 15000]).reshape(-1, 1)

        needs_targets   = incomes.flatten() * self.NEEDS_RATIO
        wants_targets   = incomes.flatten() * self.WANTS_RATIO
        savings_targets = incomes.flatten() * self.SAVINGS_RATIO

        self.needs_model.fit(incomes, needs_targets)
        self.wants_model.fit(incomes, wants_targets)
        self.savings_model.fit(incomes, savings_targets)
        self._trained = True

    # ------------------------------------------------------------------ #
    #  Recommendation                                                      #
    # ------------------------------------------------------------------ #
    def recommend(self, monthly_income, actual_needs, actual_wants):
        """
        Returns a dict with recommended and actual figures,
        personalized by blending the 50/30/20 baseline with
        the user's own spending ratios (weighted 70 / 30).
        """
        if not self._trained:
            self.train()

        if monthly_income <= 0:
            return None

        income_arr = np.array([[monthly_income]])

        # --- ML baseline (50/30/20 predictions) ---
        base_needs   = float(self.needs_model.predict(income_arr)[0])
        base_wants   = float(self.wants_model.predict(income_arr)[0])
        base_savings = float(self.savings_model.predict(income_arr)[0])

        # --- User's actual ratios ---
        actual_needs_ratio   = actual_needs  / monthly_income
        actual_wants_ratio   = actual_wants  / monthly_income
        actual_savings_ratio = max(0, 1 - actual_needs_ratio - actual_wants_ratio)

        # --- Personalised blend (70% baseline, 30% user behaviour) ---
        blended_needs   = 0.70 * base_needs   + 0.30 * actual_needs_ratio   * monthly_income
        blended_wants   = 0.70 * base_wants   + 0.30 * actual_wants_ratio   * monthly_income
        blended_savings = 0.70 * base_savings + 0.30 * actual_savings_ratio * monthly_income

        return {
            "monthly_income":   monthly_income,
            "rec_needs":        blended_needs,
            "rec_wants":        blended_wants,
            "rec_savings":      blended_savings,
            "actual_needs":     actual_needs,
            "actual_wants":     actual_wants,
            "actual_savings":   monthly_income - actual_needs - actual_wants,
            "base_needs":       base_needs,
            "base_wants":       base_wants,
            "base_savings":     base_savings,
        }

    # ------------------------------------------------------------------ #
    #  Report                                                              #
    # ------------------------------------------------------------------ #
    def display_report(self, monthly_income, actual_needs, actual_wants):
        """Print a formatted budget recommendation report to the console."""
        if monthly_income <= 0:
            print("\033[31mCannot generate report: monthly income is $0.00.\033[0m")
            print("Please set your weekly wage in the Wages menu first.")
            return

        r = self.recommend(monthly_income, actual_needs, actual_wants)
        if r is None:
            return

        sep = "=" * 52
        thin = "-" * 52

        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   💡  BUDGET RECOMMENDATION REPORT\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print(f"  Monthly Income   : \033[33m${r['monthly_income']:>10.2f}\033[0m")
        print(thin)
        print(f"  {'Category':<18} {'Recommended':>12}  {'Actual':>10}")
        print(thin)

        # Needs row
        needs_color = "\033[31m" if r['actual_needs'] > r['rec_needs'] else "\033[32m"
        print(f"  {'Needs (50%)':<18} ${r['rec_needs']:>10.2f}  "
              f"{needs_color}${r['actual_needs']:>9.2f}\033[0m")

        # Wants row
        wants_color = "\033[31m" if r['actual_wants'] > r['rec_wants'] else "\033[32m"
        print(f"  {'Wants (30%)':<18} ${r['rec_wants']:>10.2f}  "
              f"{wants_color}${r['actual_wants']:>9.2f}\033[0m")

        # Savings row
        savings_color = "\033[31m" if r['actual_savings'] < r['rec_savings'] else "\033[32m"
        print(f"  {'Savings (20%)':<18} ${r['rec_savings']:>10.2f}  "
              f"{savings_color}${r['actual_savings']:>9.2f}\033[0m")

        print(thin)

        # ---- Personalised warnings ----
        print("\033[33m  Insights:\033[0m")
        warnings_shown = False

        if r['actual_needs'] > r['rec_needs']:
            over = r['actual_needs'] - r['rec_needs']
            print(f"  ⚠  Needs are \033[31m${over:.2f} over\033[0m the recommended limit.")
            print("     Tip: Review subscriptions and fixed costs for potential cuts.")
            warnings_shown = True

        if r['actual_wants'] > r['rec_wants']:
            over = r['actual_wants'] - r['rec_wants']
            print(f"  ⚠  Wants are \033[31m${over:.2f} over\033[0m the recommended limit.")
            print("     Tip: Wait 24 hours before non-essential purchases.")
            warnings_shown = True

        if r['actual_savings'] < r['rec_savings']:
            under = r['rec_savings'] - r['actual_savings']
            print(f"  ⚠  Savings are \033[31m${under:.2f} below\033[0m the recommended target.")
            print("     Tip: Automate a small recurring transfer to your savings account.")
            warnings_shown = True

        if not warnings_shown:
            print("  ✅  Great job! Your spending is within all recommended limits.")
            print("     Consider investing your surplus for long-term growth.")

        # ---- Allocation breakdown bar ----
        print(thin)
        print("\033[33m  50/30/20 Baseline Targets:\033[0m")
        print(f"    Needs   → ${r['base_needs']:.2f}")
        print(f"    Wants   → ${r['base_wants']:.2f}")
        print(f"    Savings → ${r['base_savings']:.2f}")
        print("\033[32m" + sep + "\033[0m")
        print()


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

        for cat, name, amount, freq in session["expenses"]:
            obj = object.__new__(Needs if cat == "needs" else Wants)
            obj.name = name
            obj.ammt = amount
            obj.freq = freq
            obj.frm  = ""
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
                        print("1. Add Needs Expenses")
                        print("2. Add Wants Expense")
                        print("3. View Expenses")
                        print("4. View Totals")
                        print("5. Affordability")
                        print("6. Set Budget")
                        print("7. Modify Budget")
                        print("8. Budget Advisor")
                        print("9. Clear All Expenses")
                        print("10. Exit")
                        num = input("Enter choice: ")

                        if num == "1":
                            e = Needs()
                            expenses.append(e)
                            necessary_total += e.monthly_amount()
                            db.save_expense("needs", e.name, e.ammt, e.freq, user_id)

                        elif num == "2":
                            ne = Wants()
                            expenses.append(ne)
                            nonnecessary_total += ne.monthly_amount()
                            db.save_expense("wants", ne.name, ne.ammt, ne.freq, user_id)

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
                            advisor.display_report(monthly_income, necessary_total, nonnecessary_total)

                        elif num == "9":
                            confirm = input("Clear ALL saved expenses? (yes/no): ")
                            if confirm.lower() == "yes":
                                expenses.clear()
                                necessary_total    = 0.0
                                nonnecessary_total = 0.0
                                db.clear_expenses(user_id)
                                print("\033[32mAll expenses cleared.\033[0m")

                        elif num == "10":
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
