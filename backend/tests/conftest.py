import os
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="famcal-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmpdir) / 'test.db'}"
os.environ["SECRET_KEY"] = "aTFRcm1Bd0hRR0RfUHhZS2dJTFVKZDZ6X1dRdG5NNTA="
os.environ["APP_VERSION"] = "test"
# Tests drive sync explicitly; the background loops would race their assertions.
os.environ["SYNC_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def local_calendar(client):
    """The 'Family' calendar created on first run."""
    return client.get("/api/calendars").json()[0]
