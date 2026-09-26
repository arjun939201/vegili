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


def test_post_creation_rejects_empty_body():
    response = client.post("/api/posts", json={"body": ""})
    assert response.status_code == 422
