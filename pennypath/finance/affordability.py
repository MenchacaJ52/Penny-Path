from pennypath.prompts import ask_float, ask_int

MAX_DEBT_TO_INCOME = 0.36   # common lender guideline: total debt payments <= 36% of gross income


def monthly_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    """Fixed monthly payment for an amortizing loan (standard annuity formula)."""
    if months <= 0:
        raise ValueError("Loan duration must be at least 1 month")
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def check(income: float, principal: float, annual_rate_pct: float, months: int) -> dict:
    """Return the payment, the 36%-rule ceiling, and whether the loan is affordable."""
    payment = monthly_payment(principal, annual_rate_pct, months)
    max_payment = income * MAX_DEBT_TO_INCOME
    return {"monthly_payment": payment, "max_allowable": max_payment,
            "affordable": payment <= max_payment, "income": income}


class Affordability:
    """CLI wrapper around check()."""

    def check_affordability(self):
        income = ask_float("What is your monthly income? $", allow_zero=False)
        principal = ask_float("How much does the item cost? $", allow_zero=False)
        rate = ask_float("What is the annual interest rate (%)? ")
        months = ask_int("How many months is the loan? ", minimum=1, maximum=600)

        r = check(income, principal, rate, months)
        if r["affordable"]:
            print(f"\033[32mYou can afford the loan. Your monthly payment will be "
                  f"${r['monthly_payment']:.2f}.\033[0m")
        else:
            print(f"\033[31mYou cannot afford the loan. Your monthly payment would be "
                  f"${r['monthly_payment']:.2f}, but the maximum allowable payment is "
                  f"${r['max_allowable']:.2f}.\033[0m")
