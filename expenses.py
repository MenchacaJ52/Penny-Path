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
