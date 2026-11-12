import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Never let tests touch the real database or require a real secret. This must run before
# the web app is imported, because it opens the default database at import time.
os.environ["PENNYPATH_DB"] = os.path.join(tempfile.mkdtemp(prefix="pennypath-tests-"), "import.db")
os.environ["SECRET_KEY"] = "test-secret"

from pennypath.database import Database  # noqa: E402


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database
    database.close()


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
