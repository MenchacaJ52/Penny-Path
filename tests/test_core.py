"""Unit tests for the pure-Python building blocks."""
import hashlib

import pytest

from pennypath import auth
from pennypath.finance.affordability import assess, monthly_payment
from pennypath.finance.debt_planner import Debt, compare, simulate
from pennypath.finance.expenses import Needs, Wants, from_rows, make_expense, summarize, to_monthly


# ── Expenses ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("amount,freq,expected", [
    (100, "Monthly", 100),
    (100, "Weekly", 100 * 52 / 12),      # not ×4: a year has 52 weeks, not 48
    (100, "Biweekly", 100 * 26 / 12),
    (100, "One Time", 100),
    (100, "weekly", 100 * 52 / 12),      # case-insensitive
])
def test_to_monthly(amount, freq, expected):
    assert to_monthly(amount, freq) == pytest.approx(expected)


def test_make_expense_picks_class_and_sanitizes_subcategory():
    e = make_expense("needs", "not-a-real-sub", "Rent", 1200, "Monthly", id=7)
    assert isinstance(e, Needs) and e.subcategory == "other" and e.id == 7
    assert isinstance(make_expense("wants", "travel", "Trip", 50, "Weekly"), Wants)


def test_from_rows_and_summarize():
    rows = [(1, "needs", "groceries", "Food", 100, "Weekly"),
            (2, "wants", "dining out", "Pizza", 30, "Monthly")]
    needs, wants = summarize(from_rows(rows))
    assert needs == pytest.approx(100 * 52 / 12)
    assert wants == pytest.approx(30)


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_register_validates(db):
    assert auth.register(db, "", "password123", "password123")[1]
    assert "8 characters" in auth.register(db, "bob", "short", "short")[1]
    assert "match" in auth.register(db, "bob", "password123", "password124")[1]
    user, err = auth.register(db, "bob", "password123", "password123")
    assert err is None and user["username"] == "bob"
    assert "taken" in auth.register(db, "bob", "password123", "password123")[1]


def test_passwords_are_salted_scrypt_hashes(db):
    auth.register(db, "a", "samepassword", "samepassword")
    auth.register(db, "b", "samepassword", "samepassword")
    ha, hb = db.get_user("a")[2], db.get_user("b")[2]
    assert ha.startswith("scrypt:") and ha != hb      # per-user salt


def test_authenticate(db):
    auth.register(db, "carol", "password123", "password123")
    assert auth.authenticate(db, "carol", "password123")["username"] == "carol"
    assert auth.authenticate(db, "carol", "wrong-password") is None
    assert auth.authenticate(db, "nobody", "password123") is None


def test_legacy_sha256_hash_is_upgraded_on_login(db):
    legacy = hashlib.sha256(b"pennypath_salt_2024oldpass").hexdigest()
    db.create_user("old", legacy)
    assert auth.authenticate(db, "old", "oldpass") is not None
    upgraded = db.get_user("old")[2]
    assert upgraded.startswith("scrypt:")
    assert auth.authenticate(db, "old", "oldpass") is not None   # still works after upgrade


# ── Affordability ─────────────────────────────────────────────────────────────

def test_monthly_payment_matches_known_value():
    # $20,000 at 6% APR over 60 months → $386.66/month (standard amortization)
    assert monthly_payment(20000, 6, 60) == pytest.approx(386.656, abs=0.01)
    assert monthly_payment(1200, 0, 12) == pytest.approx(100)
    with pytest.raises(ValueError):
        monthly_payment(1000, 5, 0)


DEMO_BUDGET = dict(monthly_expenses=2511.67 + 578, existing_debt_payments=620)
DEMO_INCOME = 1150 * 52 / 12   # $4,983/month


def _status(result, name):
    return next(c["status"] for c in result["checks"] if c["name"] == name)


def test_loan_that_passes_36_percent_alone_but_breaks_the_budget_is_rejected():
    """The old check approved this: $1,676/mo is under 36% of income on its own. But with
    $620 of existing debt payments and current expenses, the user would be short every month."""
    r = assess(DEMO_INCOME, 70000, 7, 48, purpose="car", **DEMO_BUDGET)
    assert r["monthly_payment"] == pytest.approx(1676.24, abs=0.01)
    assert r["monthly_payment"] < 0.36 * DEMO_INCOME          # what the old rule looked at
    assert r["verdict"] == "not_affordable"
    assert _status(r, "Debt-to-income") == "fail"             # 46% with existing debts
    assert _status(r, "Monthly cash flow") == "fail"          # about -$403/month
    assert r["left_over"] == pytest.approx(-402.57, abs=0.01)


def test_reasonable_car_loan_is_comfortable():
    r = assess(DEMO_INCOME, 25000, 7, 60, down_payment=5000, purpose="car", **DEMO_BUDGET)
    assert r["verdict"] == "comfortable" and r["principal"] == 20000
    assert all(c["status"] == "pass" for c in r["checks"])
    assert r["total_interest"] == pytest.approx(r["monthly_payment"] * 60 - 20000)


def test_tight_when_only_the_guideline_is_exceeded():
    # Lots of slack in the budget, but a $900 car payment is 18% of income (> 15%).
    r = assess(5000, 45000, 6, 60, purpose="car")
    assert _status(r, "Payment guideline") == "warn"
    assert _status(r, "Debt-to-income") == "pass" and _status(r, "Monthly cash flow") == "pass"
    assert r["verdict"] == "tight"


def test_assess_validates_inputs():
    with pytest.raises(ValueError):
        assess(0, 1000, 5, 12)
    with pytest.raises(ValueError):
        assess(3000, 1000, 5, 12, down_payment=1000)    # down payment must be < price
    with pytest.raises(ValueError):
        assess(3000, 1000, 5, 12, purpose="yacht")


# ── Debt planner ──────────────────────────────────────────────────────────────

def test_single_debt_matches_amortization_formula():
    pay = monthly_payment(10000, 6, 60)
    r = simulate([Debt("loan", 10000, 6, pay)], extra=0, strategy="avalanche")
    assert r["finished"] and r["months"] == 60
    assert r["total_interest"] == pytest.approx(pay * 60 - 10000, abs=0.05)


def test_avalanche_never_costs_more_than_snowball():
    debts = [Debt("Card", 8000, 24.99, 200), Debt("Medical", 1200, 0, 50),
             Debt("Loan", 4000, 11, 120)]
    c = compare(debts, extra=250)
    a, s = c["results"]["avalanche"], c["results"]["snowball"]
    assert a["total_interest"] < s["total_interest"]
    assert c["interest_saved_by_avalanche"] > 0
    assert a["payoff_order"][0]["name"] == "Card"      # highest APR cleared first
    assert s["payoff_order"][0]["name"] == "Medical"   # smallest balance cleared first
    assert s["payoff_order"][0]["month"] < a["payoff_order"][0]["month"]   # the quick win


def test_minimum_below_interest_never_finishes_and_warns():
    debts = [Debt("Bad", 10000, 30, 100)]          # $250/mo interest > $100 minimum
    assert simulate(debts, 0, "snowball")["finished"] is False
    assert compare(debts, 0)["warnings"]
    assert simulate(debts, 500, "snowball")["finished"]   # extra payment fixes it
