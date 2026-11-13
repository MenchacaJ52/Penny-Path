"""Filesystem locations used across PennyPath, all relative to the project root."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(ROOT, "data")          # datasets shipped with the repo
MODELS_DIR = os.path.join(ROOT, "models")      # trained models (generated, git-ignored)

LEGACY_SQLITE_DB = os.path.join(ROOT, "pennypath.db")       # pre-Postgres data, for migration only
SECRET_KEY_FILE = os.path.join(ROOT, ".secret_key")         # git-ignored

HOUSE_PRICES_CSV = os.path.join(DATA_DIR, "fredgraph.csv")
HOUSEHOLDS_CSV = os.path.join(DATA_DIR, "penny_path_users.csv")
TRANSACTIONS_CSV = os.path.join(DATA_DIR, "penny_path_expenses.csv")
TIPS_JSON = os.path.join(DATA_DIR, "financial_tips.json")
