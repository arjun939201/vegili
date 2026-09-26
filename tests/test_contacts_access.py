import os
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_contacts_list_requires_authentication():
    response = client.get("/api/contacts")
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in"


def test_user_search_requires_authentication():
    response = client.get("/api/users/search", params={"email": "abc"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in"
