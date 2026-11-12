from pennypath.prompts import ask_choice, ask_float

# Pay/charge periods per year, used to convert any frequency to a monthly figure.
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "monthly": 12}
FREQUENCIES = ["Monthly", "Weekly", "Biweekly", "One Time"]


def to_monthly(amount: float, freq: str) -> float:
    """Monthly equivalent of a charge. One-time charges count fully in the month they occur."""
    periods = PERIODS_PER_YEAR.get(freq.strip().lower())
    return amount * periods / 12 if periods else amount


class Expense:
    """A single expense. Use Needs/Wants (or make_expense) rather than this class directly."""
    CATEGORY = ""
    LABEL = ""
    SUBCATEGORIES: list[str] = []

    def __init__(self, name: str, amount: float, freq: str = "Monthly",
                 subcategory: str = "other", id: int | None = None):
        self.id = id
        self.name = name
        self.amount = float(amount)
        self.freq = freq
        self.subcategory = subcategory if subcategory in self.SUBCATEGORIES else "other"

    @classmethod
    def prompt(cls):
        """Build an expense interactively from the console (CLI)."""
        name = ""
        while not name:
            name = input("What is the name of the expense? ").strip()
        amount = ask_float("How much is the expense? $", allow_zero=False)
        print("\n  How often is the charge?")
        freq = ask_choice("  Choose frequency number: ", FREQUENCIES)
        print(f"\n  Sub-categories ({cls.LABEL}):")
        sub = ask_choice("  Choose sub-category number: ", cls.SUBCATEGORIES)
        return cls(name, amount, freq, sub)

    def monthly_amount(self) -> float:
        return to_monthly(self.amount, self.freq)

    def to_dict(self) -> dict:
        return dict(id=self.id, name=self.name, amount=self.amount, freq=self.freq,
                    subcategory=self.subcategory, category=self.CATEGORY,
                    monthly=self.monthly_amount())

    def view_expense(self):
        print(self.LABEL)
        print("Name:", self.name)
        print("Sub-category:", self.subcategory.title())
        print(f"Amount: ${self.amount:,.2f}")
        print("Frequency:", self.freq)
        print(f"Monthly Equivalent: ${self.monthly_amount():,.2f}")


class Needs(Expense):
    CATEGORY = "needs"
    LABEL = "Necessary"
    SUBCATEGORIES = [
        "groceries", "rent/mortgage", "utilities", "gas/transport",
        "insurance", "bills", "healthcare", "childcare", "other"
    ]


class Wants(Expense):
    CATEGORY = "wants"
    LABEL = "Non-Necessary"
    SUBCATEGORIES = [
        "dining out", "entertainment", "shopping", "subscriptions",
        "hobbies", "travel", "personal care", "gifts", "other"
    ]


CATEGORIES = {"needs": Needs, "wants": Wants}


def make_expense(category: str, subcategory: str, name: str, amount: float,
                 freq: str, id: int | None = None) -> Expense:
    """Build a Needs/Wants object from stored values (e.g. a database row)."""
    return CATEGORIES.get(category, Wants)(name, amount, freq, subcategory, id)


def from_rows(rows) -> list[Expense]:
    """Build expense objects from Database.load_expenses rows."""
    return [make_expense(cat, sub, name, amount, freq, id=eid)
            for eid, cat, sub, name, amount, freq in rows]


def summarize(expenses: list[Expense]) -> tuple[float, float]:
    """Return (needs_total, wants_total) as monthly amounts."""
    needs = sum(e.monthly_amount() for e in expenses if isinstance(e, Needs))
    wants = sum(e.monthly_amount() for e in expenses if isinstance(e, Wants))
    return needs, wants


def view_totals(necessary_total, nonnecessary_total, checking_account):
    """Print monthly totals vs. checking. Read-only: does not change the balance."""
    total_expenses = necessary_total + nonnecessary_total
    remaining_balance = checking_account.balance - total_expenses

    print("\033[32m--- Expense Totals ---\033[0m")
    print(f"Total Necessary Expenses: ${necessary_total:.2f}")
    print(f"Total Non-Necessary Expenses: ${nonnecessary_total:.2f}")
    print(f"Overall Monthly Expenses: ${total_expenses:.2f}")
    print(f"Checking After Expenses: ${remaining_balance:.2f}")
    if remaining_balance < 0:
        print("\033[31mWarning: Your expenses exceed your checking balance\033[0m")
    else:
        print("\033[32mYou are within your budget.\033[0m")
