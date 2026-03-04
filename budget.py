import numpy as np
from sklearn.linear_model import LinearRegression


class Budget:
    def __init__(self, checking_balance):
        self.bd = 0

    def add_budget(self):
        self.bd = int(input("Enter Wants Budget"))

    def display_budget(self):
        print("Current wants budget: ", self.bd)

    def modify(self, checking_balance):
        new_budget = int(input("Enter new budget: "))
        while new_budget > checking_balance:
            print("New budget cannot exceed checking balance.")
            new_budget = int(input("Enter new budget: "))
        self.bd = new_budget


class BudgetAdvisor:
    """
    ML-powered budget recommendation engine.

    Trains one LinearRegression model per spending sub-category using
    benchmark ratios derived from BLS Consumer Expenditure Survey data.
    Recommendations are then personalised with a 70/30 blend of the
    baseline targets and the user's own spending ratios.
    """

    # ── Sub-category benchmark ratios (% of monthly income) ──────────────
    # Needs sub-categories  (target total ≈ 50 %)
    NEEDS_BENCHMARKS = {
        "groceries":      0.10,
        "rent/mortgage":  0.28,
        "utilities":      0.05,
        "gas/transport":  0.06,
        "insurance":      0.05,
        "bills":          0.04,
        "healthcare":     0.03,
        "childcare":      0.04,
        "other":          0.02,   # catch-all needs
    }
    # Wants sub-categories (target total ≈ 30 %)
    WANTS_BENCHMARKS = {
        "dining out":    0.05,
        "entertainment": 0.04,
        "shopping":      0.06,
        "subscriptions": 0.02,
        "hobbies":       0.03,
        "travel":        0.03,
        "personal care": 0.03,
        "gifts":         0.02,
        "other":         0.02,   # catch-all wants
    }

    # Top-level 50/30/20 ratios
    NEEDS_RATIO   = 0.50
    WANTS_RATIO   = 0.30
    SAVINGS_RATIO = 0.20

    # Training income anchor points ($500 – $15,000/mo)
    _INCOMES = np.array([500, 1000, 2000, 3000, 4000,
                         5000, 6000, 8000, 10000, 15000]).reshape(-1, 1)

    def __init__(self):
        self.needs_model   = LinearRegression()
        self.wants_model   = LinearRegression()
        self.savings_model = LinearRegression()
        self.sub_models: dict = {}
        self._trained = False

    # ------------------------------------------------------------------ #
    #  Training                                                            #
    # ------------------------------------------------------------------ #
    def train(self):
        """Fit top-level and per-subcategory linear models."""
        X = self._INCOMES
        inc = X.flatten()

        self.needs_model.fit(X,   inc * self.NEEDS_RATIO)
        self.wants_model.fit(X,   inc * self.WANTS_RATIO)
        self.savings_model.fit(X, inc * self.SAVINGS_RATIO)

        all_benchmarks = {**self.NEEDS_BENCHMARKS, **self.WANTS_BENCHMARKS}
        for sub, ratio in all_benchmarks.items():
            model = LinearRegression()
            model.fit(X, inc * ratio)
            self.sub_models[sub] = model

        self._trained = True

    # ------------------------------------------------------------------ #
    #  Recommendation                                                      #
    # ------------------------------------------------------------------ #
    def recommend(self, monthly_income: float,
                  actual_needs: float, actual_wants: float,
                  expenses: list | None = None) -> dict | None:
        """
        Returns a recommendation dict.
        expenses – list of Needs/Wants objects (used for subcategory breakdown).
        """
        if not self._trained:
            self.train()
        if monthly_income <= 0:
            return None

        X = np.array([[monthly_income]])

        base_needs   = float(self.needs_model.predict(X)[0])
        base_wants   = float(self.wants_model.predict(X)[0])
        base_savings = float(self.savings_model.predict(X)[0])

        actual_needs_ratio = actual_needs / monthly_income
        actual_wants_ratio = actual_wants / monthly_income

        blended_needs   = 0.70 * base_needs + 0.30 * actual_needs_ratio * monthly_income
        blended_wants   = 0.70 * base_wants + 0.30 * actual_wants_ratio * monthly_income
        blended_savings = monthly_income - blended_needs - blended_wants

        sub_actual: dict = {}
        if expenses:
            for exp in expenses:
                sub = getattr(exp, "subcategory", "other")
                sub_actual[sub] = sub_actual.get(sub, 0.0) + exp.monthly_amount()

        sub_recommendations: dict = {}
        all_benchmarks = {**self.NEEDS_BENCHMARKS, **self.WANTS_BENCHMARKS}
        for sub, model in self.sub_models.items():
            base_sub         = float(model.predict(X)[0])
            actual_sub       = sub_actual.get(sub, 0.0)
            actual_sub_ratio = actual_sub / monthly_income
            if actual_sub > 0:
                blended_sub = 0.70 * base_sub + 0.30 * actual_sub_ratio * monthly_income
            else:
                blended_sub = base_sub
            sub_recommendations[sub] = {
                "recommended":     blended_sub,
                "actual":          actual_sub,
                "benchmark_ratio": all_benchmarks[sub],
            }

        return {
            "monthly_income": monthly_income,
            "rec_needs":      blended_needs,
            "rec_wants":      blended_wants,
            "rec_savings":    blended_savings,
            "actual_needs":   actual_needs,
            "actual_wants":   actual_wants,
            "actual_savings": monthly_income - actual_needs - actual_wants,
            "base_needs":     base_needs,
            "base_wants":     base_wants,
            "base_savings":   base_savings,
            "subcategories":  sub_recommendations,
        }

    # ------------------------------------------------------------------ #
    #  Tips per subcategory                                                #
    # ------------------------------------------------------------------ #
    _TIPS = {
        "groceries":     "Try meal-prepping and shopping with a list to cut grocery costs.",
        "rent/mortgage": "Consider refinancing or finding a roommate to reduce housing costs.",
        "utilities":     "Unplug devices when not in use and check for better energy plans.",
        "gas/transport": "Combine errands, carpool, or use public transit to cut fuel costs.",
        "insurance":     "Shop around annually — bundling policies often saves 10–25 %.",
        "bills":         "Call providers to negotiate rates or switch to lower-cost plans.",
        "healthcare":    "Use generic medications and preventive care to reduce costs.",
        "childcare":     "Look into dependent care FSAs or local subsidy programmes.",
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

    # ------------------------------------------------------------------ #
    #  Training Results                                                    #
    # ------------------------------------------------------------------ #
    def show_training_results(self):
        """Display R², RMSE, and MAE for all trained models against the anchor data."""
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

        if not self._trained:
            self.train()

        X   = self._INCOMES
        inc = X.flatten()

        sep  = "=" * 65
        thin = "-" * 65

        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   📊  BUDGET ADVISOR – MODEL TRAINING RESULTS\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print("  Training set: 10 BLS-derived income anchor points ($500–$15,000)\n")

        print(f"  \033[33mTop-Level Categories (50/30/20 rule)\033[0m")
        print(f"  {thin}")
        print(f"  {'Model':<20}  {'R²':>8}  {'RMSE':>10}  {'MAE':>10}")
        print(f"  {thin}")

        top_models = [
            ("Needs   (50%)", self.needs_model,   inc * self.NEEDS_RATIO),
            ("Wants   (30%)", self.wants_model,   inc * self.WANTS_RATIO),
            ("Savings (20%)", self.savings_model, inc * self.SAVINGS_RATIO),
        ]
        for label, model, y_true in top_models:
            y_pred = model.predict(X)
            r2   = r2_score(y_true, y_pred)
            rmse = mean_squared_error(y_true, y_pred) ** 0.5
            mae  = mean_absolute_error(y_true, y_pred)
            r2_color = "\033[32m" if r2 >= 0.99 else ("\033[33m" if r2 >= 0.90 else "\033[31m")
            print(f"  {label:<20}  {r2_color}{r2:>8.6f}\033[0m  "
                  f"${rmse:>8,.2f}  ${mae:>8,.2f}")

        print(f"  {thin}\n")

        all_benchmarks = {**self.NEEDS_BENCHMARKS, **self.WANTS_BENCHMARKS}
        needs_subs = list(self.NEEDS_BENCHMARKS.keys())
        wants_subs = list(self.WANTS_BENCHMARKS.keys())

        for group_label, sub_keys in [("NEEDS Sub-categories", needs_subs),
                                       ("WANTS Sub-categories", wants_subs)]:
            print(f"  \033[33m{group_label}\033[0m")
            print(f"  {thin}")
            print(f"  {'Subcategory':<22}  {'Benchmark':>9}  {'R²':>8}  {'RMSE':>10}  {'MAE':>10}")
            print(f"  {thin}")
            for sub in sub_keys:
                ratio   = all_benchmarks[sub]
                y_true  = inc * ratio
                y_pred  = self.sub_models[sub].predict(X)
                r2      = r2_score(y_true, y_pred)
                rmse    = mean_squared_error(y_true, y_pred) ** 0.5
                mae     = mean_absolute_error(y_true, y_pred)
                r2_color = "\033[32m" if r2 >= 0.99 else ("\033[33m" if r2 >= 0.90 else "\033[31m")
                print(f"  {sub.title():<22}  {ratio*100:>8.0f}%  "
                      f"{r2_color}{r2:>8.6f}\033[0m  "
                      f"${rmse:>8,.2f}  ${mae:>8,.2f}")
            print(f"  {thin}\n")

        print("  \033[33mNote:\033[0m R² = 1.000000 is expected — linear models fit")
        print("  perfectly deterministic linear targets by design.")
        print("  RMSE / MAE in USD show absolute fit error at each anchor point.")
        print("\033[32m" + sep + "\033[0m\n")

    # ------------------------------------------------------------------ #
    #  Report                                                              #
    # ------------------------------------------------------------------ #
    def display_report(self, monthly_income: float,
                       actual_needs: float, actual_wants: float,
                       expenses: list | None = None):
        """Print a detailed, subcategory-level budget report."""
        if monthly_income <= 0:
            print("\033[31mCannot generate report: monthly income is $0.00.\033[0m")
            print("Please set your weekly wage in the Wages menu first.")
            return

        r = self.recommend(monthly_income, actual_needs, actual_wants, expenses)
        if r is None:
            return

        sep  = "=" * 58
        thin = "-" * 58

        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   💡  BUDGET RECOMMENDATION REPORT\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print(f"  Monthly Income   : \033[33m${r['monthly_income']:>10.2f}\033[0m")
        print(thin)

        print(f"  {'Category':<20} {'Recommended':>12}  {'Actual':>10}")
        print(thin)

        def _color(actual, rec, higher_is_bad=True):
            if higher_is_bad:
                return "\033[31m" if actual > rec else "\033[32m"
            return "\033[31m" if actual < rec else "\033[32m"

        nc = _color(r['actual_needs'],   r['rec_needs'])
        wc = _color(r['actual_wants'],   r['rec_wants'])
        sc = _color(r['actual_savings'], r['rec_savings'], higher_is_bad=False)

        print(f"  {'Needs (50%)':<20} ${r['rec_needs']:>10.2f}  "
              f"{nc}${r['actual_needs']:>9.2f}\033[0m")
        print(f"  {'Wants (30%)':<20} ${r['rec_wants']:>10.2f}  "
              f"{wc}${r['actual_wants']:>9.2f}\033[0m")
        print(f"  {'Savings (20%)':<20} ${r['rec_savings']:>10.2f}  "
              f"{sc}${r['actual_savings']:>9.2f}\033[0m")
        print(thin)

        subs = r["subcategories"]
        has_any = any(v["actual"] > 0 for v in subs.values())

        if has_any:
            print("\033[33m  📊  Subcategory Breakdown:\033[0m")
            print(f"  {'Subcategory':<22} {'Benchmark %':>11}  {'Recommended':>12}  {'Actual':>10}")
            print(thin)

            needs_subs = list(self.NEEDS_BENCHMARKS.keys())
            wants_subs = list(self.WANTS_BENCHMARKS.keys())

            def _print_group(label, sub_keys):
                print(f"  \033[36m── {label} ──\033[0m")
                for sub in sub_keys:
                    info = subs[sub]
                    pct  = f"{info['benchmark_ratio']*100:.0f}%"
                    rec  = info["recommended"]
                    act  = info["actual"]
                    color = _color(act, rec) if act > 0 else "\033[90m"
                    act_str = f"{color}${act:>9.2f}\033[0m" if act > 0 else "\033[90m       ---\033[0m"
                    print(f"  {sub.title():<22} {pct:>11}  ${rec:>10.2f}  {act_str}")

            _print_group("NEEDS", needs_subs)
            _print_group("WANTS", wants_subs)
            print(thin)

        print("\033[33m  💬  Insights:\033[0m")
        insights_shown = False

        if r['actual_needs'] > r['rec_needs']:
            over = r['actual_needs'] - r['rec_needs']
            print(f"  ⚠  Needs are \033[31m${over:.2f} over\033[0m the recommended limit.")
            insights_shown = True

        if r['actual_wants'] > r['rec_wants']:
            over = r['actual_wants'] - r['rec_wants']
            print(f"  ⚠  Wants are \033[31m${over:.2f} over\033[0m the recommended limit.")
            insights_shown = True

        if r['actual_savings'] < r['rec_savings']:
            under = r['rec_savings'] - r['actual_savings']
            print(f"  ⚠  Savings are \033[31m${under:.2f} below\033[0m the recommended target.")
            print("     Tip: Automate a small recurring transfer to your savings account.")
            insights_shown = True

        for sub, info in subs.items():
            if info["actual"] > 0 and info["actual"] > info["recommended"]:
                over = info["actual"] - info["recommended"]
                tip  = self._TIPS.get(sub, "")
                print(f"  ⚠  \033[33m{sub.title()}\033[0m is "
                      f"\033[31m${over:.2f} over\033[0m its target.")
                if tip:
                    print(f"     💡 {tip}")
                insights_shown = True

        if not insights_shown:
            print("  ✅  Great job! Spending is within all recommended limits.")
            print("     Consider investing your surplus for long-term growth.")

        print(thin)
        print("\033[33m  50/30/20 Baseline Targets:\033[0m")
        print(f"    Needs   → ${r['base_needs']:.2f}")
        print(f"    Wants   → ${r['base_wants']:.2f}")
        print(f"    Savings → ${r['base_savings']:.2f}")
        print("\033[32m" + sep + "\033[0m")
        print()

        show_tr = input("  Show model training results (R², RMSE, MAE)? (yes/no): ").strip().lower()
        if show_tr == "yes":
            self.show_training_results()
