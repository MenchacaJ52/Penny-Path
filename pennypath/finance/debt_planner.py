"""
debt_planner.py  —  Compare debt payoff strategies month by month.

  • Avalanche: put every extra dollar on the highest-APR debt first
    (mathematically minimizes total interest).
  • Snowball:  put every extra dollar on the smallest balance first
    (clears accounts sooner — a motivational win).

Each month: interest accrues on every balance, every debt gets its minimum
payment, then the extra budget — plus minimums freed up by debts already paid
off — goes to the strategy's current target.
"""
from dataclasses import dataclass

MAX_MONTHS = 600   # 50 years: anything longer is reported as "never paid off"
STRATEGIES = {
    "avalanche": "Highest interest rate first",
    "snowball":  "Smallest balance first",
}


@dataclass
class Debt:
    name: str
    balance: float
    apr: float           # annual percentage rate, e.g. 22.9
    min_payment: float


def simulate(debts: list[Debt], extra: float, strategy: str) -> dict:
    """Run a payoff simulation. Returns months, total interest, payoff order, and the
    total balance at the end of each month (for charting)."""
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")
    balances = [d.balance for d in debts]
    rates = [d.apr / 100 / 12 for d in debts]
    paid_off_month: list[int | None] = [None] * len(debts)
    interest_total = 0.0
    history = [round(sum(balances), 2)]

    def priority(i):
        return (-debts[i].apr, debts[i].balance) if strategy == "avalanche" \
               else (debts[i].balance, -debts[i].apr)
    order = sorted(range(len(debts)), key=priority)

    month = 0
    while any(b > 0.005 for b in balances) and month < MAX_MONTHS:
        month += 1
        # 1. Interest accrues.
        for i, b in enumerate(balances):
            if b > 0:
                interest = b * rates[i]
                balances[i] += interest
                interest_total += interest
        # 2. Minimum payments; minimums of paid-off debts roll into the extra budget.
        budget = extra
        for i, d in enumerate(debts):
            if balances[i] <= 0.005:
                budget += d.min_payment
                continue
            pay = min(d.min_payment, balances[i])
            balances[i] -= pay
            budget += d.min_payment - pay
        # 3. Extra payment to targets in strategy order.
        for i in order:
            if budget <= 0:
                break
            if balances[i] > 0.005:
                pay = min(budget, balances[i])
                balances[i] -= pay
                budget -= pay
        for i, b in enumerate(balances):
            if b <= 0.005 and paid_off_month[i] is None:
                balances[i] = 0.0
                paid_off_month[i] = month
        history.append(round(sum(balances), 2))

    finished = all(m is not None for m in paid_off_month)
    payoff_order = sorted(
        ({"name": debts[i].name, "month": paid_off_month[i]} for i in range(len(debts))
         if paid_off_month[i] is not None),
        key=lambda p: p["month"])
    return {
        "strategy": strategy,
        "label": STRATEGIES[strategy],
        "finished": finished,
        "months": month if finished else None,
        "total_interest": round(interest_total, 2),
        "total_paid": round(sum(d.balance for d in debts) + interest_total, 2),
        "payoff_order": payoff_order,
        "balance_history": history,
    }


def compare(debts: list[Debt], extra: float) -> dict:
    """Run both strategies and summarize the difference."""
    if not debts:
        raise ValueError("Add at least one debt first")
    results = {s: simulate(debts, extra, s) for s in STRATEGIES}
    a, s = results["avalanche"], results["snowball"]
    first_win = {k: r["payoff_order"][0] if r["payoff_order"] else None
                 for k, r in results.items()}
    stuck = [d.name for d in debts if d.balance * d.apr / 100 / 12 >= d.min_payment]
    return {
        "results": results,
        "interest_saved_by_avalanche": round(s["total_interest"] - a["total_interest"], 2),
        "first_payoff": first_win,
        "total_debt": round(sum(d.balance for d in debts), 2),
        "total_minimums": round(sum(d.min_payment for d in debts), 2),
        "warnings": [f"{name}: the minimum payment doesn't cover the monthly interest."
                     for name in stuck] if extra <= 0 else [],
    }
