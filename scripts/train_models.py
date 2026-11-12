"""
train_models.py  —  Train and evaluate both PennyPath models, then cache them.

    python scripts/train_models.py            # train (or load cache) and print evaluation
    python scripts/train_models.py --force    # retrain the Budget AI even if a cache exists

Writes models/budget_advisor.joblib and models/metrics.json. The apps load the
cache at startup and only retrain when the data or model version changes.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root

from pennypath.ml.budget import BudgetAdvisor  # noqa: E402
from pennypath.ml.home_savings_plan import HomeSavingsPlan  # noqa: E402
from pennypath.paths import MODELS_DIR  # noqa: E402


def main(force: bool = False):
    start = time.time()
    advisor = BudgetAdvisor()
    advisor.train(force=force)
    advisor.show_training_results()
    print(f"(Budget AI ready in {time.time() - start:.1f}s)\n")

    home = HomeSavingsPlan()
    home.show_training_results()

    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(os.path.join(MODELS_DIR, "metrics.json"), "w") as f:
        json.dump({"budget_advisor": advisor.model_card(), "home_price": home.model_card()},
                  f, indent=2, default=float)
    print("\nSaved models/budget_advisor.joblib and models/metrics.json")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
