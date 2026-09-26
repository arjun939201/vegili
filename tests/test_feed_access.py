import os
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_feed_requires_authenticated_user():
    response = client.get("/api/feed")
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in"
