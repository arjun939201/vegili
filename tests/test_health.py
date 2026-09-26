import os
import tempfile

# Set an isolated SQLite database before importing the application so tests
# never connect to a developer's or production database.
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app, db_session

client = TestClient(app)


class WorkingDB:
    def execute(self, statement):
        return 1


class UnavailableDB:
    def execute(self, statement):
        raise RuntimeError("database unavailable")


def override_db(db):
    def dependency():
        return db
    return dependency


def test_health_reports_process_is_up():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_database_query_succeeds():
    app.dependency_overrides[db_session] = override_db(WorkingDB())
    try:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    finally:
        app.dependency_overrides.clear()


def test_ready_returns_503_when_database_query_fails():
    app.dependency_overrides[db_session] = override_db(UnavailableDB())
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database is not ready"}
    finally:
        app.dependency_overrides.clear()


def test_current_user_endpoint_rejects_unauthenticated_request():
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Please sign in"}


def test_current_user_endpoint_rejects_invalid_session_cookie():
    client.cookies.set("vegili_session", "not-a-valid-session")
    try:
        response = client.get("/api/me")
        assert response.status_code == 401
    finally:
        client.cookies.clear()


def test_logout_clears_session_cookie():
    client.cookies.set("vegili_session", "test-session")
    try:
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert "vegili_session" in response.headers.get("set-cookie", "")
    finally:
        client.cookies.clear()
