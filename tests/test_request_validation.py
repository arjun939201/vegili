import os
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_registration_rejects_invalid_email():
    response = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "not-an-email", "password": "long-enough-password"},
    )
    assert response.status_code == 422


def test_registration_rejects_short_password():
    response = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_registration_rejects_short_name():
    response = client.post(
        "/api/auth/register",
        json={"name": "A", "email": "valid@example.com", "password": "long-enough-password"},
    )
    assert response.status_code == 422


def test_registration_rejects_missing_required_fields():
    response = client.post("/api/auth/register", json={"email": "valid@example.com"})
    assert response.status_code == 422


def test_login_rejects_invalid_email():
    response = client.post(
        "/api/auth/login",
        json={"email": "not-an-email", "password": "some-password"},
    )
    assert response.status_code == 422


def test_verification_rejects_code_with_wrong_length():
    response = client.post(
        "/api/auth/verify",
        json={"email": "valid@example.com", "code": "123"},
    )
    assert response.status_code == 422
