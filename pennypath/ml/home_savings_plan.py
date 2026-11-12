"""
home_savings_plan.py  —  Home price forecasting + down-payment savings plan.

Data: FRED median sales price of houses sold, quarterly, 1963–present, for the
US and four Census regions (data/fredgraph.csv).

Model selection is done honestly for a time series:
  • Chronological split — fit on quarters before 2015, test on 2015 onward.
    (A random split would let the model "see the future" and overstate accuracy.)
  • Candidates: a linear trend on price, a log-linear trend (constant growth
    rate) on all history, and a log-linear trend on the last 20 years.
  • A naive "price stays at its last value" forecast is reported as a baseline.
The candidate with the lowest test MAPE is refit on all data and used for
forecasting. The 95% band comes from that model's out-of-sample log error.
"""
import datetime
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from pennypath.finance.affordability import monthly_payment
from pennypath.paths import HOUSE_PRICES_CSV
from pennypath.prompts import ask_choice, ask_float, ask_int

CSV_FILE = HOUSE_PRICES_CSV
REGIONS = {
    "MSPUS": "United States",
    "MSPNE": "Northeast",
    "MSPMW": "Midwest",
    "MSPS":  "South",
    "MSPW":  "West",
}
SPLIT_DATE = pd.Timestamp("2015-01-01")
RECENT_YEARS = 20
Z_95 = 1.96


def _years(dates) -> np.ndarray:
    """Dates as fractional years (e.g. 2015.25) — a readable regression feature."""
    d = pd.to_datetime(pd.Series(dates))
    return (d.dt.year + (d.dt.dayofyear - 1) / 365.25).to_numpy()


class _TrendModel:
    """Linear regression of price (or log price) on time, optionally on a recent window."""

    def __init__(self, log: bool, window_years: int | None = None):
        self.log, self.window_years = log, window_years
        self._lr = LinearRegression()

    def fit(self, t: np.ndarray, price: np.ndarray):
        if self.window_years:
            keep = t >= t.max() - self.window_years
            t, price = t[keep], price[keep]
        self._lr.fit(t.reshape(-1, 1), np.log(price) if self.log else price)
        return self

    def predict(self, t) -> np.ndarray:
        y = self._lr.predict(np.asarray(t, dtype=float).reshape(-1, 1))
        return np.exp(y) if self.log else y

    @property
    def annual_growth(self) -> float | None:
        return float(np.expm1(self._lr.coef_[0])) if self.log else None


CANDIDATES = {
    "Linear trend":                    lambda: _TrendModel(log=False),
    "Log-linear trend (all history)":  lambda: _TrendModel(log=True),
    f"Log-linear trend (last {RECENT_YEARS} yrs)": lambda: _TrendModel(log=True,
                                                                       window_years=RECENT_YEARS),
}


class HomeSavingsPlan:
    REGIONS = REGIONS
    DOWN_PAYMENT_PCTS = [
        (0.03, "3%  – Conventional minimum (with PMI)"),
        (0.05, "5%  – Low down payment"),
        (0.10, "10% – Moderate down payment"),
        (0.20, "20% – Avoid PMI (recommended)"),
        (0.25, "25% – Strong equity position"),
    ]

    def __init__(self, csv_file: str = CSV_FILE):
        self.csv_file = csv_file
        self.df: pd.DataFrame | None = None
        self.models: dict[str, _TrendModel] = {}
        self.metrics: dict[str, dict] = {}
        self._trained = False
        if os.path.exists(csv_file):
            self._train()
        else:
            print(f"\033[31m  [HomeSavingsPlan] '{csv_file}' not found — feature unavailable.\033[0m")

    @property
    def trained(self) -> bool:
        return self._trained

    # ── Training & evaluation ─────────────────────────────────────────────
    def _train(self):
        df = pd.read_csv(self.csv_file, parse_dates=["observation_date"])
        df["t"] = _years(df["observation_date"])
        self.df = df
        is_train = df["observation_date"] < SPLIT_DATE
        t_tr, t_te, t_all = df.loc[is_train, "t"].to_numpy(), df.loc[~is_train, "t"].to_numpy(), \
                            df["t"].to_numpy()

        for col in REGIONS:
            y_tr, y_te = df.loc[is_train, col].to_numpy(), df.loc[~is_train, col].to_numpy()
            results = {}
            for name, make in CANDIDATES.items():
                pred = make().fit(t_tr, y_tr).predict(t_te)
                results[name] = self._score(y_te, pred)
            naive = self._score(y_te, np.full_like(y_te, y_tr[-1], dtype=float))

            best = min(results, key=lambda n: results[n]["mape"])
            self.models[col] = CANDIDATES[best]().fit(t_all, df[col].to_numpy())
            self.metrics[col] = {
                "chosen": best,
                "test_mape": results[best]["mape"],
                "test_mae": results[best]["mae"],
                "log_rmse": results[best]["log_rmse"],
                "naive_mape": naive["mape"],
                "annual_growth": self.models[col].annual_growth,
                "candidates": {n: r["mape"] for n, r in results.items()},
            }
        self.test_period = (f"{SPLIT_DATE.year}–{df['observation_date'].iloc[-1].year}")
        self.train_period = f"{df['observation_date'].iloc[0].year}–{SPLIT_DATE.year - 1}"
        self._trained = True

    @staticmethod
    def _score(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        y_pred = np.maximum(y_pred, 1.0)
        return {
            "mape": round(float(np.mean(np.abs(y_pred - y_true) / y_true)) * 100, 1),
            "mae": round(float(np.mean(np.abs(y_pred - y_true)))),
            "log_rmse": float(np.sqrt(np.mean((np.log(y_pred) - np.log(y_true)) ** 2))),
        }

    def model_card(self) -> dict:
        return {"train_period": self.train_period, "test_period": self.test_period,
                "candidates": list(CANDIDATES), "regions": {
                    col: {"name": REGIONS[col], **m} for col, m in self.metrics.items()}}

    # ── Forecasting ───────────────────────────────────────────────────────
    def latest(self, col: str) -> tuple[float, str]:
        row = self.df.iloc[-1]
        return float(row[col]), row["observation_date"].strftime("%Y-%m")

    def forecast(self, col: str, year: int) -> dict:
        """Mid-year price forecast with a 95% band from out-of-sample error."""
        price = float(self.models[col].predict([year + 0.5])[0])
        spread = np.exp(Z_95 * self.metrics[col]["log_rmse"])
        return {"price": price, "low": price / spread, "high": price * spread,
                "model": self.metrics[col]["chosen"]}

    @staticmethod
    def months_until(year: int, today: datetime.date | None = None) -> int:
        """Months from today until mid-year of `year` (minimum 1)."""
        today = today or datetime.date.today()
        return max(1, (year - today.year) * 12 + (7 - today.month))

    @staticmethod
    def savings_plan(target_price: float, down_pct: float, current_savings: float,
                     months_remaining: int, annual_rate: float = 0.065,
                     loan_term_years: int = 30) -> dict:
        """Down payment still needed, monthly savings to get there, and the mortgage payment.
        `annual_rate` is a fraction (0.065 = 6.5%)."""
        down_payment = target_price * down_pct
        still_needed = max(0.0, down_payment - current_savings)
        loan = target_price - down_payment
        return {
            "down_payment":    down_payment,
            "already_saved":   current_savings,
            "still_needed":    still_needed,
            "monthly_needed":  still_needed / max(1, months_remaining),
            "monthly_payment": monthly_payment(loan, annual_rate * 100, loan_term_years * 12)
                               if loan > 0 else 0.0,
        }

    # ── Chart ─────────────────────────────────────────────────────────────
    def figure(self, col: str, target_year: int, savings: float, down_pct: float,
               dark: bool = True):
        """Matplotlib figure: history, fitted trend, forecast with 95% band, and goals."""
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        fg, muted, grid, bg = (("#e2e8f0", "#94a3b8", "#2d2d44", "#1a1a2e") if dark
                               else ("#1f2937", "#4b5563", "#d1d5db", "#ffffff"))
        df, model = self.df, self.models[col]
        fc = self.forecast(col, target_year)
        last_t = df["t"].iloc[-1]
        fut_t = np.linspace(last_t, target_year + 0.5, 40)
        fut_dates = pd.to_datetime([f"{int(y)}-01-01" for y in fut_t]) + \
            pd.to_timedelta((fut_t % 1) * 365.25, unit="D")
        spread = np.exp(Z_95 * self.metrics[col]["log_rmse"])
        fut_price = model.predict(fut_t)

        fig, ax = plt.subplots(figsize=(11, 5), facecolor=bg)
        ax.set_facecolor(bg)
        ax.scatter(df["observation_date"], df[col], s=9, color="#3b82f6", alpha=0.75,
                   label="Historical median price (FRED)")
        fitted = df[df["t"] >= last_t - model.window_years] if model.window_years else df
        ax.plot(fitted["observation_date"], model.predict(fitted["t"]), color="#ef4444", lw=1.1,
                ls="--", label=f"{fc['model']} fit")
        ax.plot(fut_dates, fut_price, color="#ef4444", lw=2, label="Forecast")
        ax.fill_between(fut_dates, fut_price / spread, fut_price * spread, color="#ef4444",
                        alpha=0.15, label="95% range")
        ax.axvline(SPLIT_DATE, color=muted, lw=0.8, ls=":")
        ax.text(SPLIT_DATE, ax.get_ylim()[1] * 0.97, " test period →", color=muted, fontsize=8,
                va="top")
        dp = fc["price"] * down_pct
        ax.axhline(dp, color="#f59e0b", lw=1.2, ls="-.", label=f"Down payment needed ${dp:,.0f}")
        ax.axhline(savings, color="#22c55e", lw=1.2, ls="-.", label=f"Your savings ${savings:,.0f}")

        ax.xaxis.set_major_locator(mdates.YearLocator(10))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
        ax.tick_params(colors=muted)
        for spine in ax.spines.values():
            spine.set_edgecolor(grid)
        ax.grid(True, alpha=0.4, color=grid)
        ax.set_ylabel("Median home price", color=muted)
        ax.set_title(f"{REGIONS[col]} · {target_year} forecast ${fc['price']:,.0f} "
                     f"(95%: ${fc['low']:,.0f}–${fc['high']:,.0f})", color=fg, pad=10)
        ax.legend(fontsize=8, facecolor=bg, edgecolor=grid, labelcolor=fg, loc="upper left")
        fig.tight_layout()
        return fig

    # ── CLI ───────────────────────────────────────────────────────────────
    def show_training_results(self):
        print(f"\n\033[1;32mHOME PRICE MODEL — EVALUATION\033[0m")
        print(f"Trained on {self.train_period}, tested on {self.test_period} (chronological split)")
        names = list(CANDIDATES)
        print(f"{'Region':<15}" + "".join(f"{n[:22]:>24}" for n in names) + f"{'Naive':>8}")
        for col, m in self.metrics.items():
            cells = "".join(f"{m['candidates'][n]:>23.1f}%" for n in names)
            print(f"{REGIONS[col]:<15}{cells}{m['naive_mape']:>7.1f}%")
        print("Test MAPE (mean absolute % error) — lower is better. The best model per region is used.")

    def run(self, savings_balance: float, monthly_income: float):
        """Interactive CLI session."""
        if not self._trained:
            print("\033[31m  Home savings plan unavailable (CSV not loaded).\033[0m")
            return
        print("\n\033[1;32m🏠  HOME SAVINGS PLAN\033[0m")
        print("\n  Select your target region:")
        region_name = ask_choice("  Region number: ", list(REGIONS.values()))
        col = next(c for c, n in REGIONS.items() if n == region_name)
        this_year = datetime.date.today().year
        year = ask_int(f"  Target purchase year ({this_year}–{this_year + 30}): ",
                       this_year, this_year + 30)
        print("\n  Select down-payment percentage:")
        labels = [label for _, label in self.DOWN_PAYMENT_PCTS]
        down_pct = self.DOWN_PAYMENT_PCTS[labels.index(ask_choice("  Choice: ", labels))][0]
        print(f"\n  Your savings balance: ${savings_balance:,.2f}")
        if input("  Use this as your home savings? (yes/no): ").strip().lower() != "yes":
            savings_balance = ask_float("  Enter current home-savings amount: $")

        fc = self.forecast(col, year)
        months = self.months_until(year)
        plan = self.savings_plan(fc["price"], down_pct, savings_balance, months)
        latest, as_of = self.latest(col)

        print(f"\n  {region_name}: latest median ${latest:,.0f} ({as_of})")
        print(f"  Forecast for {year}: \033[33m${fc['price']:,.0f}\033[0m "
              f"(95% range ${fc['low']:,.0f}–${fc['high']:,.0f}, {fc['model']})")
        print(f"  Down payment ({down_pct:.0%}): ${plan['down_payment']:,.0f}  ·  "
              f"still needed ${plan['still_needed']:,.0f}")
        max_save = monthly_income * 0.20
        color = "\033[32m" if plan["monthly_needed"] <= max_save else "\033[31m"
        print(f"  Save {color}${plan['monthly_needed']:,.2f}/month\033[0m for {months} months  ·  "
              f"est. mortgage ${plan['monthly_payment']:,.2f}/month")
        if monthly_income <= 0:
            print("  ⚠  Set your weekly wage to compare against your income.")
        elif plan["monthly_needed"] > max_save:
            print(f"  ⚠  That's more than 20% of your income (${max_save:,.2f}/mo). "
                  "Consider a later year or a smaller down payment.")
        else:
            print("  ✅  That fits within a 20% savings rate.")

        if input("\n  Show price forecast chart? (yes/no): ").strip().lower() == "yes":
            import matplotlib.pyplot as plt
            self.figure(col, year, savings_balance, down_pct, dark=False)
            plt.show()
        if input("  Show model evaluation? (yes/no): ").strip().lower() == "yes":
            self.show_training_results()
