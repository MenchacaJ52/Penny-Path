"""Tests for the ML models: sensible behavior and honest evaluation."""
import datetime

import numpy as np
import pytest

from pennypath.finance.expenses import make_expense


# ── Budget Advisor ────────────────────────────────────────────────────────────

def test_recommendation_shape(advisor):
    exp = [make_expense("needs", "rent/mortgage", "Rent", 1500, "Monthly")]
    r = advisor.recommend(5000, 1500, 0, exp, household_size=1, age=30)
    assert r["rec_needs"] > 0 and r["rec_wants"] > 0
    assert r["rec_savings"] == pytest.approx(5000 - r["rec_needs"] - r["rec_wants"])
    rent = next(s for s in r["subcategories"] if s["subcategory"] == "rent/mortgage")
    assert rent["actual"] == 1500 and rent["recommended"] > 0
    assert len(r["subcategories"]) == 18


def test_engel_curve_shape(advisor):
    """Necessities' share of income falls as income rises; luxuries' share rises."""
    def share(income, cat, sub):
        r = advisor.recommend(income, 0, 0, household_size=2, age=35)
        s = next(x for x in r["subcategories"] if x["category"] == cat and x["subcategory"] == sub)
        return s["recommended"] / income
    assert share(3000, "needs", "rent/mortgage") > share(12000, "needs", "rent/mortgage")
    assert share(3000, "wants", "travel") < share(12000, "wants", "travel")


def test_bigger_household_needs_more_groceries(advisor):
    g = lambda hh: next(s["recommended"] for s in advisor.recommend(5000, 0, 0, household_size=hh,
                                                                     age=35)["subcategories"]
                        if s["subcategory"] == "groceries")
    assert g(4) > g(1)


def test_model_beats_fixed_share_baseline_and_is_calibrated(advisor):
    card = advisor.model_card()
    assert card["totals"]["total_needs"]["improvement_pct"] > 20
    assert card["beats_baseline"] >= card["targets"] // 2
    # Coverage: about 25% of held-out households should spend at or below the prediction.
    assert abs(card["mean_coverage"] - card["quantile"]) < 0.05


def test_no_recommendation_without_income(advisor):
    assert advisor.recommend(0, 0, 0) is None


def test_report_lines_render(advisor):
    r = advisor.recommend(4000, 3000, 900)
    text = "\n".join(t for t, _ in advisor.report_lines(r))
    assert "Needs" in text and "50/30/20" in text


# ── Home price model ──────────────────────────────────────────────────────────

def test_split_is_chronological(home_plan):
    train_end = int(home_plan.train_period.split("–")[1])
    test_start = int(home_plan.test_period.split("–")[0])
    assert train_end < test_start


def test_chosen_model_beats_naive_baseline(home_plan):
    for col, m in home_plan.metrics.items():
        assert m["test_mape"] == min(m["candidates"].values())
        assert m["test_mape"] < m["naive_mape"], col


def test_forecast_band_and_growth(home_plan):
    year = datetime.date.today().year + 5
    for col in home_plan.REGIONS:
        fc = home_plan.forecast(col, year)
        assert fc["low"] < fc["price"] < fc["high"]
        later = home_plan.forecast(col, year + 5)["price"]
        assert later > fc["price"]                       # positive long-run trend


def test_savings_plan_math(home_plan):
    p = home_plan.savings_plan(400000, 0.20, 30000, 50, annual_rate=0.06, loan_term_years=30)
    assert p["down_payment"] == pytest.approx(80000)
    assert p["still_needed"] == pytest.approx(50000)
    assert p["monthly_needed"] == pytest.approx(1000)
    assert p["monthly_payment"] == pytest.approx(1918.56, abs=0.05)   # $320k, 6%, 30 yrs


def test_months_until_targets_mid_year():
    from pennypath.ml.home_savings_plan import HomeSavingsPlan
    assert HomeSavingsPlan.months_until(2030, datetime.date(2026, 11, 9)) == 44
    assert HomeSavingsPlan.months_until(2026, datetime.date(2026, 11, 9)) == 1   # never < 1


# ── Tips search ───────────────────────────────────────────────────────────────

def test_tips_search_ranks_exact_question_first():
    from pennypath.assistant.tips import library
    hits = library().search("how big should my emergency fund be")
    assert hits[0]["question"] == "how much should my emergency fund be"


@pytest.mark.parametrize("q", ["what is the capital of france", "write me a poem",
                               "who won the world cup", "best way to learn guitar"])
def test_tips_offline_answer_declines_off_topic(q):
    from pennypath.assistant.tips import library
    assert library().best_answer(q) is None
