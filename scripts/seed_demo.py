"""
seed_demo.py  —  Create (or reset) a demo account with realistic sample data.

    python scripts/seed_demo.py                 # seeds pennypath.db
    python scripts/seed_demo.py --db demo.db    # seeds a separate database file

Login: demo / demo1234   (local demo data only — not a real account)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root

from pennypath import auth  # noqa: E402
from pennypath.database import Database  # noqa: E402

DEMO_USER, DEMO_PASSWORD = "demo", "demo1234"

PROFILE = dict(full_name="Alex Rivera", age=29, household_size=1, email="alex@example.com",
               occupation="IT support specialist", state="Texas", primary_goal="buy a home",
               risk_tolerance="moderate", pay_frequency="biweekly")
WEEKLY_WAGE = 1150.0
BALANCES = {"checking": 3200.0, "savings": 9500.0}
EXPENSES = [  # (category, subcategory, name, amount, frequency)
    ("needs", "rent/mortgage", "Apartment rent",   1450, "Monthly"),
    ("needs", "groceries",     "Groceries",          95, "Weekly"),
    ("needs", "utilities",     "Electric & water",  140, "Monthly"),
    ("needs", "gas/transport", "Gas",                45, "Weekly"),
    ("needs", "insurance",     "Car insurance",     160, "Monthly"),
    ("needs", "bills",         "Phone & internet",  125, "Monthly"),
    ("needs", "healthcare",    "Prescriptions",      30, "Monthly"),
    ("wants", "dining out",    "Restaurants",        60, "Weekly"),
    ("wants", "subscriptions", "Streaming + gym",    58, "Monthly"),
    ("wants", "shopping",      "Clothes & misc",    150, "Monthly"),
    ("wants", "entertainment", "Concerts & games",   70, "Monthly"),
    ("wants", "personal care", "Haircuts",           40, "Monthly"),
]
DEBTS = [  # (name, balance, apr, min_payment)
    ("Medical bill",      900,   0.00,  50),
    ("Visa credit card", 4200,  24.99, 120),
    ("Car loan",         9800,   6.90, 285),
    ("Student loan",    14500,   4.99, 165),
]


def seed(db: Database):
    row = db.get_user(DEMO_USER)
    if row is None:
        user, error = auth.register(db, DEMO_USER, DEMO_PASSWORD, DEMO_PASSWORD)
        if error:
            raise SystemExit(error)
        uid = user["id"]
    else:
        uid = row[0]
        db.update_password(uid, auth.hash_password(DEMO_PASSWORD))
        db.clear_expenses(uid)
        for d in db.load_debts(uid):
            db.delete_debt(d["id"], uid)

    db.save_wage(WEEKLY_WAGE, uid)
    for acct, bal in BALANCES.items():
        db.save_account(acct, bal, uid)
    db.save_profile(uid, PROFILE)
    for exp in EXPENSES:
        db.save_expense(*exp, uid)
    for debt in DEBTS:
        db.add_debt(uid, *debt)
    db.mark_onboarded(uid)
    print(f"Seeded '{DEMO_USER}' (password: {DEMO_PASSWORD}) in {db.path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--db", help="database file (default: pennypath.db)")
    seed(Database(parser.parse_args().db))
