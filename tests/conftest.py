"""Test configuration: isolated SQLite database and the offline mock LLM provider."""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="bookgen-tests-"))

# Must be set before any backend module is imported (settings are read at import time).
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EXPORT_DIR"] = str(_TMP / "exports")
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASS"] = ""
os.environ["TEAMS_WEBHOOK_URL"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from backend.database import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def book(client):
    res = client.post(
        "/books/",
        json={"title": "Test Book", "notes_on_outline_before": "A practical guide for beginners."},
    )
    assert res.status_code == 201, res.text
    return res.json()
