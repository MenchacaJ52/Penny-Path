import os
import sys
import uuid

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _test_database_url() -> str | None:
    """TEST_DATABASE_URL if set, else DATABASE_URL pointed at the `pennypath_test` database."""
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    if os.environ.get("DATABASE_URL"):
        return make_conninfo(os.environ["DATABASE_URL"], dbname="pennypath_test")
    return None


TEST_DATABASE_URL = _test_database_url()
if TEST_DATABASE_URL and os.environ.get("DATABASE_URL") and \
        conninfo_to_dict(TEST_DATABASE_URL).get("dbname") == \
        conninfo_to_dict(os.environ["DATABASE_URL"]).get("dbname"):
    raise SystemExit("Refusing to run: the test database is the same as the app database.")
# Anything that builds a Database() from the environment during tests (e.g. the web
# app at import time) must point at the test database, never the real one.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or ""
os.environ["SECRET_KEY"] = "test-secret"

from pennypath.database import Database  # noqa: E402


@pytest.fixture
def db():
    """A Database in a fresh, empty schema of the test database, dropped afterwards."""
    if not TEST_DATABASE_URL:
        pytest.skip("Database tests need PostgreSQL: set DATABASE_URL (see README)")
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    database = Database(TEST_DATABASE_URL, schema=schema, max_size=4)
    yield database
    database.close()
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(scope="session")
def advisor():
    from pennypath.ml.budget import BudgetAdvisor
    a = BudgetAdvisor()
    a.train()            # uses models/ cache when present
    return a


@pytest.fixture(scope="session")
def home_plan():
    from pennypath.ml.home_savings_plan import HomeSavingsPlan
    return HomeSavingsPlan()


@pytest.fixture
def app(db, monkeypatch):
    from pennypath.ui import web
    monkeypatch.setattr(web, "db", db)
    web.app.config.update(TESTING=True)
    return web


@pytest.fixture
def client(app):
    return app.app.test_client()


def register(client, username="alice", password="password123"):
    r = client.post("/api/auth/register",
                    json=dict(username=username, password=password, confirm=password))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.fixture
def user(client):
    """A registered, onboarded, logged-in user ($1,000/week)."""
    u = register(client)
    client.post("/api/onboarding", json=dict(wage=1000, savings=5000, debt=0))
    return u
