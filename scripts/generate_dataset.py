"""
generate_dataset.py
Generates the synthetic household-spending data used to train the Budget AI.

  data/penny_path_users.csv    – one row per household (income, size, age, monthly spend per subcategory)
  data/penny_path_expenses.csv – one row per recurring charge, for the same households

The data is SYNTHETIC, but its structure follows well-documented consumer
spending patterns rather than fixed percentages:

  • Engel curves — spending on a category scales as income**elasticity.
    Necessities (rent, groceries, utilities) have elasticity < 1, so their
    *share* of income falls as income rises; luxuries (travel, dining out)
    have elasticity > 1, so their share rises. Shares at a $5,000/month
    reference income match the BLS-style benchmarks in budget.py.
  • Household size raises groceries, utilities, and housing; childcare only
    appears for larger households with working-age adults.
  • Age raises healthcare spending.
  • Each household has a latent "spending personality" that scales all of
    its discretionary spending, plus independent noise per category.

As in real survey data, many low-income households spend more than they earn.

Run from the project root:  python scripts/generate_dataset.py
Then retrain:               python scripts/train_models.py --force
"""

import csv
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
from pennypath.paths import DATA_DIR  # noqa: E402

random.seed(42)

REF_INCOME = 5000.0   # monthly income at which the shares below hold exactly

# subcategory: (share of income at REF_INCOME, income elasticity)
NEEDS_PARAMS = {
    "groceries":     (0.10, 0.45),
    "rent/mortgage": (0.28, 0.60),
    "utilities":     (0.05, 0.35),
    "gas/transport": (0.06, 0.70),
    "insurance":     (0.05, 0.75),
    "bills":         (0.04, 0.50),
    "healthcare":    (0.03, 0.55),
    "childcare":     (0.10, 0.80),   # share among households that have childcare
    "other":         (0.02, 0.80),
}
WANTS_PARAMS = {
    "dining out":    (0.05, 1.10),
    "entertainment": (0.04, 1.00),
    "shopping":      (0.06, 1.05),
    "subscriptions": (0.02, 0.40),
    "hobbies":       (0.03, 1.10),
    "travel":        (0.03, 1.50),
    "personal care": (0.03, 0.80),
    "gifts":         (0.02, 1.00),
    "other":         (0.02, 1.00),
}
NEEDS_SUBCATEGORIES = list(NEEDS_PARAMS)
WANTS_SUBCATEGORIES = list(WANTS_PARAMS)

FREQUENCIES = ["monthly", "weekly", "biweekly", "one time"]
FREQ_WEIGHTS = [0.55, 0.20, 0.20, 0.05]
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "monthly": 12, "one time": 12}

HOUSEHOLD_SIZES = [1, 2, 3, 4, 5]
HOUSEHOLD_WEIGHTS = [0.28, 0.34, 0.15, 0.13, 0.10]


def safe_name(text: str) -> str:
    return text.replace("/", "_").replace(" ", "_")


def _lognormal(sigma: float) -> float:
    """Multiplicative noise with median 1."""
    return math.exp(random.gauss(0, sigma))


def _engel(income: float, share: float, elasticity: float) -> float:
    """Monthly spend predicted by a constant-elasticity Engel curve."""
    return REF_INCOME * share * (income / REF_INCOME) ** elasticity


def generate_household() -> dict:
    income = min(30000.0, max(1200.0, 5000.0 * _lognormal(0.6)))
    size = random.choices(HOUSEHOLD_SIZES, weights=HOUSEHOLD_WEIGHTS)[0]
    age = random.randint(20, 75)
    personality = 0.8 * _lognormal(0.35)   # >1 = spender, <1 = frugal (affects wants)

    spend = {}
    for sub, (share, elas) in NEEDS_PARAMS.items():
        base = _engel(income, share, elas)
        if sub == "groceries":
            base *= size ** 0.6 / 2 ** 0.6
        elif sub == "utilities":
            base *= 1 + 0.15 * (size - 2)
        elif sub == "rent/mortgage":
            base *= 1 + 0.12 * (size - 2)
        elif sub == "healthcare":
            base *= max(0.5, 1 + (age - 40) / 40)
        elif sub == "childcare":
            has_kids = size >= 3 and age < 50 and random.random() < 0.7
            base = base * (size - 2) ** 0.5 if has_kids else 0.0
        spend[f"needs_{safe_name(sub)}"] = base * _lognormal(0.20)

    for sub, (share, elas) in WANTS_PARAMS.items():
        if random.random() < 0.15:   # some households skip a category entirely
            spend[f"wants_{safe_name(sub)}"] = 0.0
            continue
        base = _engel(income, share, elas) * personality
        if sub == "travel":
            base *= 1 + max(0, age - 55) / 40
        spend[f"wants_{safe_name(sub)}"] = base * _lognormal(0.30)

    spend = {k: round(v, 2) for k, v in spend.items()}
    total_needs = sum(v for k, v in spend.items() if k.startswith("needs_"))
    total_wants = sum(v for k, v in spend.items() if k.startswith("wants_"))
    savings = income - total_needs - total_wants
    savings_rate = savings / income
    status = "over" if savings < 0 else "tight" if savings_rate < 0.10 else "healthy"

    return {
        "monthly_income": round(income, 2),
        "household_size": size,
        "age": age,
        "total_needs": round(total_needs, 2),
        "total_wants": round(total_wants, 2),
        "actual_savings": round(savings, 2),
        "savings_rate": round(savings_rate, 4),
        "budget_status": status,
        **spend,
    }


def generate(n: int = 3000, users_file: str = "penny_path_users.csv",
             expenses_file: str = "penny_path_expenses.csv"):
    households = [generate_household() for _ in range(n)]
    sub_cols = ([f"needs_{safe_name(s)}" for s in NEEDS_SUBCATEGORIES] +
                [f"wants_{safe_name(s)}" for s in WANTS_SUBCATEGORIES])
    user_fields = ["user_id", "monthly_income", "household_size", "age", "total_needs",
                   "total_wants", "actual_savings", "savings_rate", "budget_status"] + sub_cols

    with open(os.path.join(DATA_DIR, users_file), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=user_fields)
        writer.writeheader()
        for uid, h in enumerate(households, 1):
            writer.writerow({"user_id": uid, **h})

    # Transaction-level view of the same households: each subcategory's monthly
    # spend expressed as a charge at a randomly chosen frequency.
    with open(os.path.join(DATA_DIR, expenses_file), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "user_id", "monthly_income", "category", "subcategory",
            "amount", "frequency", "monthly_equivalent"])
        writer.writeheader()
        for uid, h in enumerate(households, 1):
            for cat, subs in (("needs", NEEDS_SUBCATEGORIES), ("wants", WANTS_SUBCATEGORIES)):
                for sub in subs:
                    monthly = h[f"{cat}_{safe_name(sub)}"]
                    if monthly <= 0:
                        continue
                    freq = random.choices(FREQUENCIES, weights=FREQ_WEIGHTS)[0]
                    writer.writerow({
                        "user_id": uid, "monthly_income": h["monthly_income"],
                        "category": cat, "subcategory": sub,
                        "amount": round(monthly * 12 / PERIODS_PER_YEAR[freq], 2),
                        "frequency": freq, "monthly_equivalent": monthly,
                    })

    statuses = [h["budget_status"] for h in households]
    print(f"[users]    {n} households -> {users_file}")
    print(f"[expenses] transaction rows -> {expenses_file}")
    print("budget status mix:", {s: statuses.count(s) for s in ("healthy", "tight", "over")})


if __name__ == "__main__":
    generate()
