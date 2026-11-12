"""
cli.py  —  PennyPath command-line app.
Run from the project root:  python run_cli.py
"""
import time

from pennypath.database import Database
from pennypath.auth import login_screen
from pennypath.finance.accounts import SavingsAccount, CheckingAccount, WageAccount
from pennypath.finance.wages import Wages
from pennypath.finance.expenses import Needs, Wants, from_rows, summarize, view_totals
from pennypath.finance.affordability import Affordability
from pennypath.ml.budget import Budget, BudgetAdvisor
from pennypath.ml.home_savings_plan import HomeSavingsPlan
from pennypath.assistant.tips import tips_menu

GREEN, YELLOW, RED, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def print_delay(text, delay=0.1):
    for letter in text:
        print(letter, end='', flush=True)
        time.sleep(delay)


class CLISession:
    """One logged-in user's state, loaded from and saved to the database."""

    def __init__(self, db: Database, user: dict):
        self.db = db
        self.user_id = user["id"]
        self.username = user["username"]
        self.savings = SavingsAccount()
        self.checking = CheckingAccount()
        self.wage_account = WageAccount()
        self.wages = Wages()
        self.expenses = []
        self.budget: Budget | None = None
        self.load()

    # ── Persistence ───────────────────────────────────────────────────────
    def load(self):
        s = self.db.load_session(self.user_id)
        self.savings.balance = s["savings"]
        self.checking.balance = s["checking"]
        self.wage_account.balance = s["wage_account"]
        self.wages.weekly_wage = s["wage"]
        self.expenses = from_rows(s["expenses"])
        self.budget = None
        if s["budget"] > 0:
            self.budget = Budget()
            self.budget.bd = s["budget"]
        if any([self.savings.balance, self.checking.balance, self.wages.weekly_wage]):
            print(f"{GREEN}✔ Previous session restored.{RESET}")

    def save(self):
        self.db.save_session(self.savings.balance, self.checking.balance, self.wages.weekly_wage,
                             self.budget.bd if self.budget else None, self.user_id,
                             wage_account_bal=self.wage_account.balance)

    @property
    def totals(self) -> tuple[float, float]:
        return summarize(self.expenses)

    # ── Menus ─────────────────────────────────────────────────────────────
    def main_menu(self) -> str:
        print(f"\n{GREEN}MAIN MENU{RESET}  {YELLOW}[{self.username}]{RESET}")
        print("1. Savings")
        print("2. Checking")
        print("3. Budget & Affordability")
        print("4. Wage")
        print("5. Tips")
        print("6. Logout")
        print("7. Exit")
        return input("Please choose an option: ").strip()

    def add_expense(self, cls):
        e = cls.prompt()
        e.id = self.db.save_expense(e.CATEGORY, e.subcategory, e.name, e.amount, e.freq,
                                    self.user_id)
        self.expenses.append(e)
        print(f"{GREEN}✔ Added {e.name} (${e.monthly_amount():,.2f}/month).{RESET}")

    def show_totals(self):
        needs, wants = self.totals
        view_totals(needs, wants, self.checking)
        if self.budget is None:
            print(f"{YELLOW}No wants budget set. Use option 6.{RESET}")
            return
        left = self.budget.bd - wants
        if wants >= self.budget.bd:
            print(f"{RED}You have spent your monthly wants budget.{RESET}")
        elif wants >= self.budget.bd * 0.9:
            print(f"{YELLOW}You have spent more than 90% of your wants budget.{RESET}")
        print(f"Wants budget left: ${left:,.2f}")

    def budget_menu(self, advisor: BudgetAdvisor, home_plan: HomeSavingsPlan):
        while True:
            print(f"{GREEN}BUDGET & AFFORDABILITY MENU{RESET}")
            print("1.  Add Needs Expense")
            print("2.  Add Wants Expense")
            print("3.  View Expenses")
            print("4.  View Totals")
            print("5.  Affordability")
            print("6.  Set Wants Budget")
            print("7.  Budget Advisor")
            print("8.  Clear All Expenses")
            print("9.  Home Savings Plan")
            print("10. Exit")
            num = input("Enter choice: ").strip()

            if num == "1":
                self.add_expense(Needs)
            elif num == "2":
                self.add_expense(Wants)
            elif num == "3":
                if not self.expenses:
                    print(f"{YELLOW}No expenses yet.{RESET}")
                for e in self.expenses:
                    e.view_expense()
                    print()
            elif num == "4":
                self.show_totals()
            elif num == "5":
                Affordability().check_affordability()
            elif num == "6":
                self.budget = self.budget or Budget()
                self.budget.set_budget()
                self.db.save_budget(self.budget.bd, self.user_id)
            elif num == "7":
                needs, wants = self.totals
                advisor.display_report(self.wages.monthly_income, needs, wants, self.expenses)
            elif num == "8":
                if input("Clear ALL saved expenses? (yes/no): ").strip().lower() == "yes":
                    self.expenses.clear()
                    self.db.clear_expenses(self.user_id)
                    print(f"{GREEN}All expenses cleared.{RESET}")
            elif num == "9":
                home_plan.run(self.savings.balance, self.wages.monthly_income)
            elif num == "10":
                return
            else:
                print(f"{RED}Invalid choice.{RESET}")


def main():
    db = Database()
    print("Loading models…")
    advisor = BudgetAdvisor()
    advisor.train()
    home_plan = HomeSavingsPlan()

    session = CLISession(db, login_screen(db))
    print_delay(f"{GREEN}Welcome to PennyPath{RESET}\n", .03)

    while True:
        option = session.main_menu()
        if option == "1":
            session.savings.savings_menu(session.checking)
        elif option == "2":
            session.checking.checking_menu(session.savings)
        elif option == "3":
            session.budget_menu(advisor, home_plan)
        elif option == "4":
            session.wages.wage_menu(session.wage_account, session.savings)
        elif option == "5":
            tips_menu()
        elif option == "6":
            session.save()
            print(f"{GREEN}✔ Session saved. Logged out as {session.username}.{RESET}")
            session = CLISession(db, login_screen(db))
            continue
        elif option == "7":
            session.save()
            db.close()
            print(f"{GREEN}✔ Session saved. Goodbye!{RESET}")
            return
        else:
            print(f"{RED}Invalid option.{RESET}")
        session.save()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")
