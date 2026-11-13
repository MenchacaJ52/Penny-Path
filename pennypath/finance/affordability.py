"""
affordability.py  —  Can I afford this loan?

A loan is judged against the user's whole budget, not in isolation. Three checks:

  1. Debt-to-income: ALL monthly debt payments (existing + the new loan) as a
     share of income. Lenders typically want <= 36% and most refuse above 43%.
     Lenders use gross income; PennyPath only knows take-home pay, so this is
     slightly conservative.
  2. Cash flow: money left each month after expenses, existing debt payments,
     and the new payment. Below zero means the loan can't be paid without
     running down savings or borrowing more.
  3. Purpose guideline: common rules of thumb for the payment on its own,
     e.g. a car payment at most ~15% of take-home pay.

Each check passes, warns, or fails; the overall verdict is the worst of the three.
"""
from pennypath.prompts import ask_choice, ask_float, ask_int

DTI_GOOD, DTI_MAX = 0.36, 0.43          # lender guidelines (28/36 rule; 43% QM limit)
CASH_BUFFER = 0.10                      # want >= 10% of income left over each month
PURPOSES = {                            # payment-to-income guideline for the loan alone
    "car":      (0.15, "car payments at most 15% of take-home pay"),
    "home":     (0.28, "housing payments at most 28% of income"),
    "personal": (0.10, "a personal loan payment at most 10% of take-home pay"),
    "other":    (0.10, "a single loan payment at most 10% of take-home pay"),
}
VERDICTS = {"pass": "comfortable", "warn": "tight", "fail": "not_affordable"}


def monthly_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    """Fixed monthly payment for an amortizing loan (standard annuity formula)."""
    if months <= 0:
        raise ValueError("Loan duration must be at least 1 month")
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def assess(income: float, price: float, annual_rate_pct: float, months: int, *,
           down_payment: float = 0.0, monthly_expenses: float = 0.0,
           existing_debt_payments: float = 0.0, purpose: str = "other") -> dict:
    """Judge a loan against the user's whole monthly budget.

    income: monthly take-home pay. monthly_expenses: needs + wants (excluding debt
    payments). existing_debt_payments: minimum payments on current debts.
    """
    if income <= 0:
        raise ValueError("Income must be greater than zero")
    if not 0 <= down_payment < price:
        raise ValueError("Down payment must be at least 0 and less than the price")
    if purpose not in PURPOSES:
        raise ValueError(f"Purpose must be one of: {', '.join(PURPOSES)}")

    principal = price - down_payment
    payment = monthly_payment(principal, annual_rate_pct, months)
    total_interest = payment * months - principal

    dti = (existing_debt_payments + payment) / income
    left_over = income - monthly_expenses - existing_debt_payments - payment
    cap, cap_text = PURPOSES[purpose]
    share = payment / income

    checks = [
        {
            "name": "Debt-to-income",
            "status": "pass" if dti <= DTI_GOOD else "warn" if dti <= DTI_MAX else "fail",
            "value": dti, "limit": DTI_GOOD,
            "detail": (f"All debt payments would be {dti:.0%} of income "
                       f"(${existing_debt_payments:,.0f} existing + ${payment:,.0f} new). "
                       f"Lenders like {DTI_GOOD:.0%} or less; most refuse above {DTI_MAX:.0%}."),
        },
        {
            "name": "Monthly cash flow",
            "status": "fail" if left_over < 0 else "warn" if left_over < CASH_BUFFER * income
                      else "pass",
            "value": left_over, "limit": CASH_BUFFER * income,
            "detail": (f"{'-' if left_over < 0 else ''}${abs(left_over):,.0f}/month left after "
                       f"expenses, debt payments, and this loan."
                       + (" You'd be short every month." if left_over < 0 else
                                   f" Aim to keep at least ${CASH_BUFFER * income:,.0f} "
                                   f"({CASH_BUFFER:.0%}) as a buffer."
                                   if left_over < CASH_BUFFER * income else "")),
        },
        {
            "name": "Payment guideline",
            "status": "pass" if share <= cap else "warn",
            "value": share, "limit": cap,
            "detail": f"This payment is {share:.0%} of income; a common guideline is {cap_text}.",
        },
    ]
    worst = "fail" if any(c["status"] == "fail" for c in checks) else \
            "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    return {
        "verdict": VERDICTS[worst],
        "monthly_payment": payment,
        "principal": principal,
        "total_interest": total_interest,
        "total_cost": payment * months + down_payment,
        "income": income,
        "monthly_expenses": monthly_expenses,
        "existing_debt_payments": existing_debt_payments,
        "left_over": left_over,
        "checks": checks,
    }


VERDICT_TEXT = {
    "comfortable":    "✓ Comfortable — this loan fits your budget.",
    "tight":          "⚠ Tight — affordable on paper, but leaves little room.",
    "not_affordable": "✗ Not affordable with your current budget.",
}


class Affordability:
    """CLI wrapper around assess(), using the logged-in user's budget."""

    def check_affordability(self, monthly_income: float = 0.0, monthly_expenses: float = 0.0,
                            existing_debt_payments: float = 0.0):
        if monthly_income > 0:
            print(f"Using your monthly income of ${monthly_income:,.2f}.")
        else:
            monthly_income = ask_float("What is your monthly take-home income? $",
                                       allow_zero=False)
        price = ask_float("How much does the item cost? $", allow_zero=False)
        down = ask_float("Down payment (0 if none)? $")
        while down >= price:
            down = ask_float("The down payment must be less than the price. Down payment? $")
        rate = ask_float("What is the annual interest rate (%)? ")
        months = ask_int("How many months is the loan? ", minimum=1, maximum=600)
        print("\n  What is the loan for?")
        purpose = ask_choice("  Choose: ", list(PURPOSES))

        r = assess(monthly_income, price, rate, months, down_payment=down,
                   monthly_expenses=monthly_expenses,
                   existing_debt_payments=existing_debt_payments, purpose=purpose)
        color = {"comfortable": "\033[32m", "tight": "\033[33m",
                 "not_affordable": "\033[31m"}[r["verdict"]]
        print(f"\n{color}{VERDICT_TEXT[r['verdict']]}\033[0m")
        print(f"Monthly payment ${r['monthly_payment']:,.2f} · total interest "
              f"${r['total_interest']:,.2f}")
        icons = {"pass": "\033[32m✓\033[0m", "warn": "\033[33m⚠\033[0m", "fail": "\033[31m✗\033[0m"}
        for c in r["checks"]:
            print(f"  {icons[c['status']]} {c['name']}: {c['detail']}")
