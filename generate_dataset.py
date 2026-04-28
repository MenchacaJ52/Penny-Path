"""
generate_dataset.py
Generates two synthetic CSVs for Penny-Path ML training:

  penny_path_users.csv    – one row per user (income, balances, totals, subcategory breakdown)
  penny_path_expenses.csv – one row per expense/recurring charge (transaction-level)
"""

import csv
import random

random.seed(42)

# ── Category / subcategory definitions (mirrors budget.py) ────────────────────
NEEDS_SUBCATEGORIES = [
    "groceries", "rent/mortgage", "utilities", "gas/transport",
    "insurance", "bills", "healthcare", "childcare", "other",
]

WANTS_SUBCATEGORIES = [
    "dining out", "entertainment", "shopping", "subscriptions",
    "hobbies", "travel", "personal care", "gifts", "other",
]

NEEDS_BENCHMARKS = {
    "groceries":      0.10,
    "rent/mortgage":  0.28,
    "utilities":      0.05,
    "gas/transport":  0.06,
    "insurance":      0.05,
    "bills":          0.04,
    "healthcare":     0.03,
    "childcare":      0.04,
    "other":          0.02,
}

WANTS_BENCHMARKS = {
    "dining out":    0.05,
    "entertainment": 0.04,
    "shopping":      0.06,
    "subscriptions": 0.02,
    "hobbies":       0.03,
    "travel":        0.03,
    "personal care": 0.03,
    "gifts":         0.02,
    "other":         0.02,
}

FREQUENCIES = ["monthly", "weekly", "biweekly", "one time"]
FREQ_WEIGHTS = [0.50, 0.20, 0.20, 0.10]

# Monthly income distribution (range, weight)
INCOME_BUCKETS = [
    ((1500,  2500), 0.15),   # low income
    ((2500,  4000), 0.25),   # lower-middle
    ((4000,  6000), 0.30),   # middle
    ((6000, 10000), 0.20),   # upper-middle
    ((10000, 20000), 0.10),  # high income
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_income() -> float:
    buckets, weights = zip(*INCOME_BUCKETS)
    lo, hi = random.choices(buckets, weights=weights)[0]
    return round(random.uniform(lo, hi), 2)


def _pick_frequency() -> str:
    return random.choices(FREQUENCIES, weights=FREQ_WEIGHTS)[0]


def _to_monthly(amount: float, freq: str) -> float:
    """Convert a per-period amount to its monthly equivalent."""
    if freq == "weekly":
        return amount * 4.33
    if freq == "biweekly":
        return amount * 2.17
    return amount   # monthly or one-time: treat as-is


def _from_monthly(monthly: float, freq: str) -> float:
    """Convert a monthly amount back to the per-period charge."""
    if freq == "weekly":
        return monthly / 4.33
    if freq == "biweekly":
        return monthly / 2.17
    return monthly


def _safe_name(text: str) -> str:
    return text.replace("/", "_").replace(" ", "_")


# ── Expense generator ─────────────────────────────────────────────────────────

def _generate_expenses(monthly_income: float) -> list[dict]:
    """Return a list of expense dicts for one synthetic user."""
    expenses = []

    for sub, ratio in NEEDS_BENCHMARKS.items():
        # Childcare: only ~35 % of users have this
        if sub == "childcare" and random.random() < 0.65:
            continue
        # Needs 'other': skip ~40 % of the time
        if sub == "other" and random.random() < 0.40:
            continue

        base_monthly = monthly_income * ratio
        actual_monthly = max(0.0, base_monthly * random.uniform(0.70, 1.30))

        freq = _pick_frequency()
        period_amount = round(_from_monthly(actual_monthly, freq), 2)
        monthly_eq = round(_to_monthly(period_amount, freq), 2)

        expenses.append({
            "category":          "needs",
            "subcategory":       sub,
            "expense_name":      _safe_name(sub),
            "amount":            period_amount,
            "frequency":         freq,
            "monthly_equivalent": monthly_eq,
        })

    for sub, ratio in WANTS_BENCHMARKS.items():
        # ~25 % chance a user skips any given wants category
        if random.random() < 0.25:
            continue

        base_monthly = monthly_income * ratio
        actual_monthly = max(0.0, base_monthly * random.uniform(0.30, 1.80))

        freq = _pick_frequency()
        period_amount = round(_from_monthly(actual_monthly, freq), 2)
        monthly_eq = round(_to_monthly(period_amount, freq), 2)

        expenses.append({
            "category":          "wants",
            "subcategory":       sub,
            "expense_name":      _safe_name(sub),
            "amount":            period_amount,
            "frequency":         freq,
            "monthly_equivalent": monthly_eq,
        })

    return expenses


# ── CSV generators ────────────────────────────────────────────────────────────

def generate_users_csv(n: int = 500, output_file: str = "penny_path_users.csv"):
    """
    One row per user.
    Columns: user_id, monthly_income, weekly_wage, checking_balance,
             savings_balance, total_needs, total_wants, actual_savings,
             savings_rate, num_expenses, budget_status,
             needs_<subcategory>..., wants_<subcategory>...
    """
    needs_cols = [f"needs_{_safe_name(s)}" for s in NEEDS_SUBCATEGORIES]
    wants_cols = [f"wants_{_safe_name(s)}" for s in WANTS_SUBCATEGORIES]

    fieldnames = [
        "user_id", "monthly_income", "weekly_wage",
        "checking_balance", "savings_balance",
        "total_needs", "total_wants", "actual_savings", "savings_rate",
        "num_expenses", "budget_status",
    ] + needs_cols + wants_cols

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for uid in range(1, n + 1):
            monthly_income = _pick_income()
            weekly_wage    = round(monthly_income / 4.33, 2)
            expenses       = _generate_expenses(monthly_income)

            total_needs  = sum(e["monthly_equivalent"] for e in expenses if e["category"] == "needs")
            total_wants  = sum(e["monthly_equivalent"] for e in expenses if e["category"] == "wants")
            actual_savings = monthly_income - total_needs - total_wants
            savings_rate = round(actual_savings / monthly_income, 4)

            # Simulate a few months of accumulation
            months = random.randint(1, 6)
            checking_balance = round(max(0, actual_savings * months * random.uniform(0.3, 0.8)), 2)
            savings_balance  = round(max(0, actual_savings * months * random.uniform(0.2, 0.7)), 2)

            if actual_savings < 0:
                budget_status = "over"
            elif savings_rate < 0.10:
                budget_status = "tight"
            else:
                budget_status = "healthy"

            # Build subcategory lookup
            sub_totals: dict[str, float] = {}
            for e in expenses:
                col = f"{e['category']}_{_safe_name(e['subcategory'])}"
                sub_totals[col] = round(sub_totals.get(col, 0.0) + e["monthly_equivalent"], 2)

            row: dict = {
                "user_id":           uid,
                "monthly_income":    monthly_income,
                "weekly_wage":       weekly_wage,
                "checking_balance":  checking_balance,
                "savings_balance":   savings_balance,
                "total_needs":       round(total_needs, 2),
                "total_wants":       round(total_wants, 2),
                "actual_savings":    round(actual_savings, 2),
                "savings_rate":      savings_rate,
                "num_expenses":      len(expenses),
                "budget_status":     budget_status,
            }
            for col in needs_cols + wants_cols:
                row[col] = sub_totals.get(col, 0.0)

            writer.writerow(row)

    print(f"[users]    {n} rows -> {output_file}")


def generate_expenses_csv(n: int = 500, output_file: str = "penny_path_expenses.csv"):
    """
    One row per individual expense (recurring charges).
    Columns: user_id, monthly_income, category, subcategory,
             expense_name, amount, frequency, monthly_equivalent
    """
    fieldnames = [
        "user_id", "monthly_income", "category", "subcategory",
        "expense_name", "amount", "frequency", "monthly_equivalent",
    ]

    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for uid in range(1, n + 1):
            monthly_income = _pick_income()
            for exp in _generate_expenses(monthly_income):
                writer.writerow({
                    "user_id":           uid,
                    "monthly_income":    monthly_income,
                    "category":          exp["category"],
                    "subcategory":       exp["subcategory"],
                    "expense_name":      exp["expense_name"],
                    "amount":            exp["amount"],
                    "frequency":         exp["frequency"],
                    "monthly_equivalent": exp["monthly_equivalent"],
                })

    print(f"[expenses] {n} users -> {output_file}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    N = 500
    generate_users_csv(n=N,    output_file="penny_path_users.csv")
    generate_expenses_csv(n=N, output_file="penny_path_expenses.csv")
    print("Done.")
