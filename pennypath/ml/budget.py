"""
budget.py  —  Wants budget + the ML Budget Advisor.

The Budget Advisor answers: "for a household like mine, what do *thrifty*
households spend on each category?" It trains one quantile-regression model
per spending target (18 subcategories + total needs + total wants) on
data/penny_path_users.csv and predicts the 25th percentile of spending given
log(income), household size, and age.

For each target it compares two candidate models on a held-out 20% split —
a linear quantile regression in log-space (a classic Engel curve) and a
gradient-boosted quantile model — keeps the one with the lower pinball loss,
and reports how both compare to the old fixed-percentage baseline.

Trained models are cached in models/budget_advisor.joblib and rebuilt
automatically when the data file or MODEL_VERSION changes.
"""
import hashlib
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import QuantileRegressor
from sklearn.metrics import mean_pinball_loss
from sklearn.model_selection import train_test_split

from pennypath.paths import HOUSEHOLDS_CSV, MODELS_DIR

DATA_FILE = HOUSEHOLDS_CSV
MODEL_FILE = os.path.join(MODELS_DIR, "budget_advisor.joblib")
MODEL_VERSION = 2
OVER_TOLERANCE = 1.05   # only flag a category when it's more than 5% above peers


class Budget:
    """A monthly spending cap for the user's wants."""

    def __init__(self, checking_balance: float | None = None):   # arg kept for older callers
        self.bd = 0.0

    def set_budget(self):
        from pennypath.prompts import ask_float
        current = f" (currently ${self.bd:,.2f})" if self.bd else ""
        self.bd = ask_float(f"Enter monthly wants budget{current}: $", allow_zero=False)
        print(f"\033[32mWants budget set to ${self.bd:,.2f}/month.\033[0m")

    def display_budget(self):
        print(f"Current wants budget: ${self.bd:,.2f}")


def _col(category: str, sub: str) -> str:
    return f"{category}_{sub.replace('/', '_').replace(' ', '_')}"


class BudgetAdvisor:
    """Quantile-regression budget recommendations from peer households."""

    NEEDS_SUBS = ["groceries", "rent/mortgage", "utilities", "gas/transport",
                  "insurance", "bills", "healthcare", "childcare", "other"]
    WANTS_SUBS = ["dining out", "entertainment", "shopping", "subscriptions",
                  "hobbies", "travel", "personal care", "gifts", "other"]

    QUANTILE = 0.25   # "thrifty peers": spend less than 75% of similar households
    NEEDS_RATIO, WANTS_RATIO, SAVINGS_RATIO = 0.50, 0.30, 0.20   # classic 50/30/20 rule
    FEATURES = ["log_income", "household_size", "age"]

    _TIPS = {
        "groceries":     "Try meal-prepping and shopping with a list to cut grocery costs.",
        "rent/mortgage": "Consider refinancing or finding a roommate to reduce housing costs.",
        "utilities":     "Unplug devices when not in use and check for better energy plans.",
        "gas/transport": "Combine errands, carpool, or use public transit to cut fuel costs.",
        "insurance":     "Shop around annually — bundling policies often saves 10–25%.",
        "bills":         "Call providers to negotiate rates or switch to lower-cost plans.",
        "healthcare":    "Use generic medications and preventive care to reduce costs.",
        "childcare":     "Look into dependent care FSAs or local subsidy programs.",
        "dining out":    "Cook at home 1–2 more nights per week to trim dining costs.",
        "entertainment": "Look for free local events, libraries, and streaming bundles.",
        "shopping":      "Use a 24-hour rule before non-essential purchases.",
        "subscriptions": "Audit your subscriptions — cancel anything unused for 30+ days.",
        "hobbies":       "Borrow gear from libraries or buy second-hand equipment.",
        "travel":        "Book 6–8 weeks ahead and use points/miles to offset costs.",
        "personal care": "DIY routines and drugstore brands rival salon products.",
        "gifts":         "Set annual gift budgets per person and shop sales/off-season.",
        "other":         "Track miscellaneous spending for a month to find hidden leaks.",
    }

    def __init__(self, data_file: str = DATA_FILE, model_file: str | None = MODEL_FILE):
        self.data_file = data_file
        self.model_file = model_file
        self.models: dict = {}       # target column -> fitted estimator (predicts log1p spend)
        self.metrics: dict = {}      # target column -> evaluation summary
        self.defaults = {"household_size": 2, "age": 35}
        self._trained = False

    # ── Targets ───────────────────────────────────────────────────────────
    @classmethod
    def targets(cls) -> list[tuple[str, str, str]]:
        """(column, category, subcategory) for every model; totals use subcategory ''."""
        t = [("total_needs", "needs", ""), ("total_wants", "wants", "")]
        t += [(_col("needs", s), "needs", s) for s in cls.NEEDS_SUBS]
        t += [(_col("wants", s), "wants", s) for s in cls.WANTS_SUBS]
        return t

    # ── Training ──────────────────────────────────────────────────────────
    def _fingerprint(self) -> str:
        with open(self.data_file, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:16]
        return f"v{MODEL_VERSION}-q{self.QUANTILE}-{digest}"

    def train(self, force: bool = False):
        """Load cached models if they match the data; otherwise fit and cache them."""
        fp = self._fingerprint()
        if not force and self.model_file and os.path.exists(self.model_file):
            try:
                cached = joblib.load(self.model_file)
            except Exception:   # e.g. pickled with a different scikit-learn version
                cached = {}
            if cached.get("fingerprint") == fp:
                self.models, self.metrics = cached["models"], cached["metrics"]
                self.defaults = cached["defaults"]
                self._trained = True
                return
        print("Training Budget AI models (first run only, ~30 s)…")
        self._fit()
        if self.model_file:
            os.makedirs(os.path.dirname(self.model_file), exist_ok=True)
            joblib.dump({"fingerprint": fp, "models": self.models, "metrics": self.metrics,
                         "defaults": self.defaults}, self.model_file)

    @classmethod
    def _X(cls, df: pd.DataFrame) -> np.ndarray:
        return np.column_stack([np.log(df["monthly_income"]), df["household_size"], df["age"]])

    def _candidates(self):
        q = self.QUANTILE
        return {
            "linear quantile (log-log)": lambda: QuantileRegressor(quantile=q, alpha=0.0,
                                                                   solver="highs"),
            "gradient boosting": lambda: HistGradientBoostingRegressor(
                loss="quantile", quantile=q, max_iter=150, max_depth=3,
                learning_rate=0.05, random_state=0),
        }

    def _fit(self):
        df = pd.read_csv(self.data_file)
        self.defaults = {"household_size": int(df["household_size"].median()),
                         "age": int(df["age"].median())}
        train, test = train_test_split(df, test_size=0.2, random_state=42)
        q = self.QUANTILE

        for col, _, sub in self.targets():
            # Subcategories are zero-inflated (e.g. most households have no childcare), so
            # those models learn from households that actually have the expense: the question
            # is "what do thrifty peers *who pay for X* spend on X?". Totals use everyone.
            tr = train[train[col] > 0] if sub else train
            te = test[test[col] > 0] if sub else test
            full = df[df[col] > 0] if sub else df
            y_tr, y_te = tr[col].to_numpy(), te[col].to_numpy()

            # Baseline: the old approach — a fixed share of income
            # (here, the q-th quantile of spend/income on the training set).
            share = np.quantile(y_tr / tr["monthly_income"], q)
            base_pred = share * te["monthly_income"].to_numpy()
            base_loss = mean_pinball_loss(y_te, base_pred, alpha=q)

            results = {}
            for name, make in self._candidates().items():
                model = make().fit(self._X(tr), np.log1p(y_tr))
                pred = np.expm1(model.predict(self._X(te))).clip(min=0)
                results[name] = {"pinball_loss": mean_pinball_loss(y_te, pred, alpha=q),
                                 "coverage": float(np.mean(y_te <= pred))}

            best = min(results, key=lambda n: results[n]["pinball_loss"])
            # Refit the winner on all (relevant) data for serving.
            self.models[col] = self._candidates()[best]().fit(self._X(full),
                                                             np.log1p(full[col].to_numpy()))
            self.metrics[col] = {
                "rows": len(full),
                "model": best,
                "pinball_loss": round(results[best]["pinball_loss"], 2),
                "baseline_loss": round(base_loss, 2),
                "improvement_pct": round(100 * (1 - results[best]["pinball_loss"] / base_loss), 1)
                                   if base_loss > 0 else 0.0,
                "coverage": round(results[best]["coverage"], 3),
                "candidates": {n: round(r["pinball_loss"], 2) for n, r in results.items()},
            }
        self.metrics["_summary"] = {
            "rows": len(df), "train_rows": len(train), "test_rows": len(test),
            "quantile": q, "features": self.FEATURES,
        }
        self._trained = True

    # ── Recommendation ────────────────────────────────────────────────────
    def recommend(self, monthly_income: float, actual_needs: float, actual_wants: float,
                  expenses: list | None = None, household_size: int | None = None,
                  age: int | None = None) -> dict | None:
        """Compare the user's spending with thrifty peers. `expenses` are Needs/Wants objects."""
        if not self._trained:
            self.train()
        if monthly_income <= 0:
            return None

        hh = household_size or self.defaults["household_size"]
        age = age or self.defaults["age"]
        X = np.array([[np.log(monthly_income), hh, age]])
        predict = lambda col: max(0.0, float(np.expm1(self.models[col].predict(X)[0])))

        actual_by_col: dict[str, float] = {}
        for e in expenses or []:
            col = _col(e.CATEGORY, e.subcategory)
            actual_by_col[col] = actual_by_col.get(col, 0.0) + e.monthly_amount()

        rec_needs, rec_wants = predict("total_needs"), predict("total_wants")
        subcategories = []
        for col, cat, sub in self.targets()[2:]:
            rec = predict(col)
            subcategories.append({
                "category": cat, "subcategory": sub, "recommended": rec,
                "actual": actual_by_col.get(col, 0.0), "peer_share": rec / monthly_income,
                "tip": self._TIPS.get(sub, ""),
            })

        return {
            "monthly_income": monthly_income,
            "household_size": hh, "age": age,
            "used_defaults": household_size is None or age is None,
            "quantile": self.QUANTILE,
            "rec_needs": rec_needs, "rec_wants": rec_wants,
            "rec_savings": monthly_income - rec_needs - rec_wants,
            "actual_needs": actual_needs, "actual_wants": actual_wants,
            "actual_savings": monthly_income - actual_needs - actual_wants,
            "base_needs": monthly_income * self.NEEDS_RATIO,
            "base_wants": monthly_income * self.WANTS_RATIO,
            "base_savings": monthly_income * self.SAVINGS_RATIO,
            "subcategories": subcategories,
        }

    def model_card(self) -> dict:
        """Evaluation summary for display: overall and per-target metrics."""
        if not self._trained:
            self.train()
        per_target = {c: m for c, m in self.metrics.items() if not c.startswith("_")}
        wins = sum(m["improvement_pct"] > 0 for m in per_target.values())
        return {
            **self.metrics["_summary"],
            "targets": len(per_target),
            "beats_baseline": wins,
            "median_improvement_pct": float(np.median([m["improvement_pct"]
                                                       for m in per_target.values()])),
            "mean_coverage": round(float(np.mean([m["coverage"] for m in per_target.values()])), 3),
            "model_counts": pd.Series([m["model"] for m in per_target.values()])
                              .value_counts().to_dict(),
            "totals": {c: per_target[c] for c in ("total_needs", "total_wants")},
        }

    # ── Text report (CLI + desktop) ───────────────────────────────────────
    @staticmethod
    def report_lines(r: dict) -> list[tuple[str, str]]:
        """The recommendation as (text, tag) lines; tag ∈ {'', head, green, red, amber, muted}."""
        lines: list[tuple[str, str]] = []
        add = lambda text="", tag="": lines.append((text, tag))
        pct = int(r["quantile"] * 100)

        add("BUDGET RECOMMENDATION REPORT", "head")
        add(f"Compared with the thriftiest {pct}% of households earning "
            f"${r['monthly_income']:,.0f}/mo (household of {r['household_size']}, age {r['age']})",
            "muted")
        if r["used_defaults"]:
            add("Tip: add your age and household size to your profile for closer peers.", "muted")
        add()
        add(f"  {'Category':<22} {'Peers':>10}  {'You':>10}")
        for label, rk, ak, higher_is_bad in (("Needs", "rec_needs", "actual_needs", True),
                                             ("Wants", "rec_wants", "actual_wants", True),
                                             ("Savings", "rec_savings", "actual_savings", False)):
            over = r[ak] > r[rk] if higher_is_bad else r[ak] < r[rk]
            add(f"  {label:<22} ${r[rk]:>9,.2f}  ${r[ak]:>9,.2f}", "red" if over else "green")
        add()

        used = [s for s in r["subcategories"] if s["actual"] > 0]
        if used:
            add("Subcategory Breakdown", "head")
            for s in used:
                name = s["subcategory"].title() + (" (wants)" if s["subcategory"] == "other"
                                                    and s["category"] == "wants" else "")
                over = s["actual"] > s["recommended"] * OVER_TOLERANCE
                add(f"  {name:<22} ${s['recommended']:>9,.2f}  ${s['actual']:>9,.2f}",
                    "red" if over else "green")
            add()

        add("Insights", "head")
        shown = False
        for label, rk, ak in (("Needs", "rec_needs", "actual_needs"),
                              ("Wants", "rec_wants", "actual_wants")):
            if r[ak] > r[rk]:
                add(f"  {label} are ${r[ak] - r[rk]:,.2f} above thrifty peers.", "red")
                shown = True
        if r["actual_savings"] < r["rec_savings"]:
            add(f"  Savings are ${r['rec_savings'] - r['actual_savings']:,.2f} below thrifty peers.",
                "amber")
            add("     Tip: automate a small recurring transfer to savings.", "muted")
            shown = True
        for s in used:
            if s["actual"] > s["recommended"] * OVER_TOLERANCE and s["tip"]:
                add(f"  {s['subcategory'].title()}: ${s['actual'] - s['recommended']:,.2f} over. "
                    f"{s['tip']}", "amber")
                shown = True
        if not shown:
            add("  You're spending at or below thrifty peers in every category — great job!",
                "green")
        if r["rec_savings"] < 0:
            add("  Note: even thrifty households at this income tend to spend more than they earn;"
                " growing income may matter more than cutting.", "muted")
        add()
        add(f"50/30/20 rule for comparison: needs ${r['base_needs']:,.2f} · "
            f"wants ${r['base_wants']:,.2f} · savings ${r['base_savings']:,.2f}", "muted")
        return lines

    def display_report(self, monthly_income: float, actual_needs: float, actual_wants: float,
                       expenses: list | None = None, household_size: int | None = None,
                       age: int | None = None):
        """CLI: print the report with ANSI colors."""
        if monthly_income <= 0:
            print("\033[31mCannot generate report: monthly income is $0.00.\033[0m")
            print("Please set your weekly wage in the Wages menu first.")
            return
        r = self.recommend(monthly_income, actual_needs, actual_wants, expenses,
                           household_size, age)
        ansi = {"head": "\033[1;32m", "green": "\033[32m", "red": "\033[31m",
                "amber": "\033[33m", "muted": "\033[90m", "": ""}
        print()
        for text, tag in self.report_lines(r):
            print(f"{ansi[tag]}{text}\033[0m" if tag else text)
        if input("\nShow model evaluation? (yes/no): ").strip().lower() == "yes":
            self.show_training_results()

    def show_training_results(self):
        card = self.model_card()
        print(f"\n\033[1;32mBUDGET ADVISOR — MODEL EVALUATION\033[0m")
        print(f"{card['rows']} households · {card['train_rows']} train / {card['test_rows']} test"
              f" · predicting the {int(card['quantile'] * 100)}th percentile")
        print(f"{'Target':<26} {'Model':<26} {'Pinball':>8} {'Baseline':>9} {'Better':>7} {'Cov.':>6}")
        for col, m in self.metrics.items():
            if col.startswith("_"):
                continue
            print(f"{col:<26} {m['model']:<26} {m['pinball_loss']:>8.2f} {m['baseline_loss']:>9.2f}"
                  f" {m['improvement_pct']:>6.1f}% {m['coverage']:>6.2f}")
        print("Pinball loss: lower is better. Coverage should be near "
              f"{card['quantile']:.2f} (share of test households at or below the prediction).")
