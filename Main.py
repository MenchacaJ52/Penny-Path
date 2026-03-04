import time

from database import Database
from auth import login_screen
from accounts import SavingsAccount, CheckingAccount, WageAccount
from wages import Wages
from expenses import Needs, Wants, view_totals
from affordability import Affordability
from budget import Budget, BudgetAdvisor
from home_savings_plan import HomeSavingsPlan


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

    current_user = login_screen(db)
    user_id      = current_user["id"]
    username     = current_user["username"]

    def load_user_session():
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
                    autosave()
                    print(f"\033[32m✔ Session saved. Logged out as {username}.\033[0m")

                    savings_account  = SavingsAccount()
                    checking_account = CheckingAccount()
                    wages            = Wages()
                    expenses         = []
                    necessary_total    = 0.0
                    nonnecessary_total = 0.0
                    b                = None

                    current_user = login_screen(db)
                    user_id      = current_user["id"]
                    username     = current_user["username"]
                    load_user_session()
                    if any([savings_account.balance, checking_account.balance,
                            wages.weekly_wage]):
                        print("\033[32m✔ Previous session restored.\033[0m")
                    break

                elif option == "7":
                    autosave()
                    db.close()
                    print("\033[32m✔ Session saved. Goodbye!\033[0m")
                    return


general_program()
