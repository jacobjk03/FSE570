"""End-to-end test: Flask app routes (GET index, POST investigation)."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest

pytest.importorskip("flask", reason="Flask required for app e2e tests (install with: pip install -r requirements.txt)")


@pytest.fixture
def client():
    """Flask test client."""
    from app.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_flask_get_index(client):
    """GET / returns 200 and the index page."""
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"query" in rv.data or b"investigation" in rv.data.lower()


def test_flask_post_empty_query_shows_error(client):
    """POST with empty query returns error message."""
    rv = client.post("/", data={"query": ""}, follow_redirects=True)
    assert rv.status_code == 200
    assert b"enter" in rv.data.lower() or b"query" in rv.data.lower()


def test_flask_post_tesla_investigation(client):
    """POST with Tesla investigation query returns results page with expected structure."""
    rv = client.post("/", data={"query": "Investigate Tesla for money laundering"}, follow_redirects=False)
    assert rv.status_code == 200
    # Results page should contain some of: entity, tasks, findings, report, risk, gaps
    data = rv.data.decode("utf-8", errors="replace")
    assert "Tesla" in data or "tesla" in data or "entity" in data or "findings" in data or "report" in data
