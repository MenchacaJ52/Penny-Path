import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.model_selection import train_test_split


class HomeSavingsPlan:

    CSV_FILE = "fredgraph.csv"

    REGION_LABELS = {
        "1": ("MSPUS", "United States (National)"),
        "2": ("MSPNE", "Northeast"),
        "3": ("MSPMW", "Midwest"),
        "4": ("MSPS",  "South"),
        "5": ("MSPW",  "West"),
    }

    DOWN_PAYMENT_PCTS = {
        "1": (0.03,  "3%  – Conventional minimum (with PMI)"),
        "2": (0.05,  "5%  – Low down payment"),
        "3": (0.10,  "10% – Moderate down payment"),
        "4": (0.20,  "20% – Avoid PMI (recommended)"),
        "5": (0.25,  "25% – Strong equity position"),
    }

    def __init__(self):
        self._df         = None
        self._lr_models  = {}   # {col: LinearRegression}
        self._knn_models = {}   # {col: KNeighborsRegressor}
        self._trained    = False
        self._X_test     = None
        self._y_test     = None
        self._load_and_train()

    # ── Data & Training ───────────────────────────────────────────────
    def _load_and_train(self):
        """Load CSV and train LR + KNN models for every region column."""
        if not os.path.exists(self.CSV_FILE):
            print(f"\033[31m  [HomeSavingsPlan] '{self.CSV_FILE}' not found — "
                  f"feature unavailable.\033[0m")
            return

        df = pd.read_csv(self.CSV_FILE)
        df['observation_date'] = pd.to_datetime(df['observation_date'])
        df['date_numeric'] = df['observation_date'].astype(np.int64) / 10**9
        self._df = df

        cols = ['MSPUS', 'MSPNE', 'MSPMW', 'MSPS', 'MSPW']
        X = df['date_numeric'].values.reshape(-1, 1)
        y_all = df[cols]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_all, test_size=0.2, random_state=42
        )

        for col in cols:
            lr = LinearRegression()
            lr.fit(X_train, y_train[col])
            self._lr_models[col] = lr

            knn = KNeighborsRegressor(n_neighbors=3)
            knn.fit(X_train, y_train[col])
            self._knn_models[col] = knn

        self._trained = True
        self._X_test  = X_test
        self._y_test  = y_test

    # ── Training Results ──────────────────────────────────────────────
    def _show_training_results(self):
        """Display R², RMSE, and MAE for LR and KNN on the hold-out test set."""
        from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

        sep  = "=" * 70
        thin = "-" * 70
        cols = ['MSPUS', 'MSPNE', 'MSPMW', 'MSPS', 'MSPW']
        region_names = {
            'MSPUS': 'United States (National)',
            'MSPNE': 'Northeast',
            'MSPMW': 'Midwest',
            'MSPS':  'South',
            'MSPW':  'West',
        }

        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   📊  MODEL TRAINING RESULTS  (80/20 train-test split)\033[0m")
        print("\033[32m" + sep + "\033[0m")

        for col in cols:
            print(f"\n  \033[33m{region_names[col]}  [{col}]\033[0m")
            print(f"  {thin}")
            print(f"  {'Model':<8}  {'R²':>8}  {'RMSE':>12}  {'MAE':>12}")
            print(f"  {thin}")

            y_true = self._y_test[col].values

            for model_name, model_dict in [("LR", self._lr_models), ("KNN", self._knn_models)]:
                model  = model_dict[col]
                y_pred = model.predict(self._X_test)
                r2     = r2_score(y_true, y_pred)
                rmse   = mean_squared_error(y_true, y_pred) ** 0.5
                mae    = mean_absolute_error(y_true, y_pred)

                r2_color = "\033[32m" if r2 >= 0.90 else ("\033[33m" if r2 >= 0.70 else "\033[31m")
                print(f"  {model_name:<8}  {r2_color}{r2:>8.4f}\033[0m  "
                      f"${rmse:>10,.0f}  ${mae:>10,.0f}")

            print(f"  {thin}")

        print()
        print("\033[32m" + sep + "\033[0m")
        print("  \033[33mNote:\033[0m R² closer to 1.0 = better fit. "
              "RMSE/MAE in USD — lower is better.")
        print("\033[32m" + sep + "\033[0m")

    # ── Prediction helpers ────────────────────────────────────────────
    def _date_to_numeric(self, year: int, quarter: int = 1) -> float:
        """Convert a year + quarter (1-4) to Unix timestamp (seconds)."""
        month = (quarter - 1) * 3 + 1
        ts = pd.Timestamp(year=year, month=month, day=1)
        return float(ts.value) / 10**9

    def _predict_price(self, col: str, year: int) -> dict:
        """Return LR and KNN predicted prices for a given region and year."""
        x = np.array([[self._date_to_numeric(year)]])

        latest_price = float(self._df[col].iloc[-1])
        latest_year  = self._df['observation_date'].iloc[-1].year
        years_ahead  = max(0, year - latest_year)
        price_cap    = latest_price * (1.04 ** years_ahead)

        lr_raw  = float(self._lr_models[col].predict(x)[0])
        knn_raw = float(self._knn_models[col].predict(x)[0])

        return {
            "lr":  max(latest_price, min(lr_raw,  price_cap)),
            "knn": max(latest_price, min(knn_raw, price_cap)),
        }

    # ── Savings plan calculator ───────────────────────────────────────
    @staticmethod
    def _savings_plan(target_price: float, down_pct: float,
                      current_savings: float, months_remaining: int) -> dict:
        down_payment_needed = target_price * down_pct
        still_needed        = max(0.0, down_payment_needed - current_savings)
        monthly_needed      = still_needed / months_remaining if months_remaining > 0 else still_needed
        return {
            "down_payment":   down_payment_needed,
            "already_saved":  current_savings,
            "still_needed":   still_needed,
            "monthly_needed": monthly_needed,
        }

    # ── Chart ─────────────────────────────────────────────────────────
    def _show_chart(self, col: str, region_name: str,
                    target_year: int, predicted_lr: float, predicted_knn: float,
                    savings_balance: float, down_pct: float):
        """Plot historical prices + LR & KNN forecast lines + down-payment goal."""
        df = self._df
        X_hist = df['date_numeric'].values.reshape(-1, 1)

        last_ts   = df['date_numeric'].max()
        fut_ts    = self._date_to_numeric(target_year)
        fut_x     = np.linspace(last_ts, fut_ts, 20).reshape(-1, 1)
        fut_dates = pd.to_datetime(fut_x.flatten(), unit='s')

        lr_fut  = self._lr_models[col].predict(fut_x)
        knn_fut = self._knn_models[col].predict(fut_x)

        fig, ax = plt.subplots(figsize=(13, 6))

        ax.scatter(df['observation_date'], df[col],
                   color='steelblue', s=14, alpha=0.7, label='Historical (FRED)')

        lr_hist = self._lr_models[col].predict(X_hist)
        ax.plot(df['observation_date'], lr_hist,
                color='tomato', linewidth=1.2, linestyle='--', label='LR fit (historical)')

        ax.plot(fut_dates, lr_fut,
                color='tomato', linewidth=2, linestyle='-', label='LR forecast')
        ax.plot(fut_dates, knn_fut,
                color='darkorange', linewidth=2, linestyle='-', label='KNN forecast')

        ax.axhline(predicted_lr,  color='tomato',    linestyle=':', alpha=0.7,
                   label=f'LR target price  ${predicted_lr:,.0f}')
        ax.axhline(predicted_knn, color='darkorange', linestyle=':', alpha=0.7,
                   label=f'KNN target price ${predicted_knn:,.0f}')
        ax.axhline(savings_balance, color='limegreen', linewidth=1.5, linestyle='-.',
                   label=f'Current savings  ${savings_balance:,.0f}')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator(5))
        plt.xticks(rotation=45)
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f'${v:,.0f}')
        )
        ax.set_xlabel('Year')
        ax.set_ylabel('Median Home Price (USD)')
        ax.set_title(f'Home Price Forecast – {region_name}\n'
                     f'Target: {target_year}  |  Down payment: {down_pct*100:.0f}%')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    # ── Public entry point ────────────────────────────────────────────
    def run(self, savings_balance: float, monthly_income: float):
        """Interactive home-savings planning session."""
        if not self._trained:
            print("\033[31m  Home savings plan unavailable (CSV not loaded).\033[0m")
            return

        sep  = "=" * 60
        thin = "-" * 60
        print()
        print("\033[32m" + sep + "\033[0m")
        print("\033[32m   🏠  HOME SAVINGS PLAN\033[0m")
        print("\033[32m" + sep + "\033[0m")
        print(thin)

        # ── Step 1: Region ────────────────────────────────────────────
        print("\n  Select your target region:")
        for k, (col, label) in self.REGION_LABELS.items():
            print(f"    {k}. {label}")
        while True:
            pick = input("  Region (1-5): ").strip()
            if pick in self.REGION_LABELS:
                col, region_name = self.REGION_LABELS[pick]
                break
            print("\033[31m  Invalid choice.\033[0m")

        # ── Step 2: Target year ───────────────────────────────────────
        today         = datetime.date.today()
        current_year  = today.year
        current_month = today.month
        while True:
            try:
                target_year = int(input(f"  Target purchase year (e.g. {current_year + 5}): ").strip())
                if target_year < current_year:
                    print(f"\033[31m  Must be {current_year} or later.\033[0m")
                    continue
                break
            except ValueError:
                print("\033[31m  Enter a valid year.\033[0m")

        # ── Step 3: Down payment % ────────────────────────────────────
        print("\n  Select down-payment percentage:")
        for k, (pct, label) in self.DOWN_PAYMENT_PCTS.items():
            print(f"    {k}. {label}")
        while True:
            pick = input("  Choice (1-5): ").strip()
            if pick in self.DOWN_PAYMENT_PCTS:
                down_pct, dp_label = self.DOWN_PAYMENT_PCTS[pick]
                break
            print("\033[31m  Invalid choice.\033[0m")

        # ── Step 4: Current savings override ─────────────────────────
        print(f"\n  Your current savings account balance: \033[33m${savings_balance:,.2f}\033[0m")
        override = input("  Use this amount as your starting savings? (yes/no): ").strip().lower()
        if override != "yes":
            while True:
                try:
                    savings_balance = float(input("  Enter current home-savings amount: $").strip())
                    break
                except ValueError:
                    print("\033[31m  Enter a valid number.\033[0m")

        # ── Step 5: Predict & calculate ───────────────────────────────
        prices    = self._predict_price(col, target_year)
        lr_price  = prices["lr"]
        knn_price = prices["knn"]
        avg_price = (lr_price + knn_price) / 2

        months_remaining = max(1, (target_year - current_year) * 12 + (1 - current_month))

        lr_plan  = self._savings_plan(lr_price,  down_pct, savings_balance, months_remaining)
        knn_plan = self._savings_plan(knn_price, down_pct, savings_balance, months_remaining)
        avg_plan = self._savings_plan(avg_price, down_pct, savings_balance, months_remaining)

        last_row     = self._df.iloc[-1]
        latest_price = last_row[col]
        latest_date  = last_row['observation_date'].strftime('%Y-%m')

        # ── Report ────────────────────────────────────────────────────
        print()
        print("\033[32m" + sep + "\033[0m")
        print(f"  Region   : \033[33m{region_name}\033[0m")
        print(f"  Latest price ({latest_date}): \033[33m${latest_price:,.0f}\033[0m")
        print(f"  Target year : \033[33m{target_year}\033[0m  "
              f"({months_remaining} months away)")
        print(f"  Down payment: \033[33m{dp_label}\033[0m")
        print(thin)
        print(f"  {'Model':<10} {'Predicted Price':>16}  {'Down Payment':>13}  "
              f"{'Monthly Savings':>16}")
        print(thin)

        for label, price, plan in [
            ("LR",      lr_price,  lr_plan),
            ("KNN",     knn_price, knn_plan),
            ("Average", avg_price, avg_plan),
        ]:
            feasible = plan["monthly_needed"] <= monthly_income * 0.20
            color    = "\033[32m" if feasible else "\033[31m"
            print(f"  {label:<10} ${price:>14,.0f}  "
                  f"${plan['down_payment']:>12,.0f}  "
                  f"{color}${plan['monthly_needed']:>14,.2f}\033[0m")

        print(thin)
        print(f"  Current savings : \033[33m${savings_balance:,.2f}\033[0m")
        print(f"  Still needed    : \033[33m${avg_plan['still_needed']:,.2f}\033[0m  "
              f"(based on avg model)")
        print(thin)

        rec_monthly = avg_plan["monthly_needed"]
        max_save    = monthly_income * 0.20
        print("\033[33m  💬  Insights:\033[0m")
        if monthly_income <= 0:
            print("  ⚠  Set your weekly wage first to see income-based insights.")
        elif rec_monthly <= 0:
            print("  ✅  You already have enough saved for the down payment!")
        elif rec_monthly <= max_save:
            print(f"  ✅  Saving \033[32m${rec_monthly:,.2f}/mo\033[0m fits within your "
                  f"recommended 20% savings budget (${max_save:,.2f}/mo).")
        else:
            gap = rec_monthly - max_save
            print(f"  ⚠  You need \033[31m${rec_monthly:,.2f}/mo\033[0m but your 20% "
                  f"savings budget is only ${max_save:,.2f}/mo.")
            print(f"     To stay on track, consider extending your timeline by "
                  f"~{int(gap / (max_save / months_remaining) + months_remaining) - months_remaining} months,")
            print(f"     increasing income, or reducing expenses by \033[31m${gap:,.2f}/mo\033[0m.")

        print("\033[32m" + sep + "\033[0m")

        # ── Optional chart ────────────────────────────────────────────
        show = input("\n  Show price forecast chart? (yes/no): ").strip().lower()
        if show == "yes":
            self._show_chart(col, region_name, target_year,
                             lr_price, knn_price, savings_balance, down_pct)

        # ── Optional training results ─────────────────────────────────
        show_tr = input("\n  Show model training results (R², RMSE, MAE)? (yes/no): ").strip().lower()
        if show_tr == "yes":
            self._show_training_results()
