import os
import hashlib
import secrets
import tempfile
from datetime import datetime, timedelta, timezone

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


def register_payload():
    token = secrets.token_hex(5)
    return {
        "name": "Test Person",
        "email": f"auth-{token}@example.com",
        "password": "safe-test-password",
    }


def enable_test_otp(monkeypatch):
    monkeypatch.setattr(main, "OTP_DEV", True)
    monkeypatch.delenv("SMTP_HOST", raising=False)


def test_registration_verification_and_login_lifecycle(monkeypatch):
    enable_test_otp(monkeypatch)
    client.cookies.clear()
    payload = register_payload()

    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 200
    code = registered.json()["dev_code"]
    assert isinstance(code, str) and len(code) == 6

    wrong_code = "000000" if code != "000000" else "000001"
    rejected = client.post(
        "/api/auth/verify",
        json={"email": payload["email"], "code": wrong_code},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "Incorrect verification code"

    verified = client.post(
        "/api/auth/verify",
        json={"email": payload["email"], "code": code},
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["email"] == payload["email"]
    assert "vegili_session" in client.cookies

    client.cookies.clear()
    bad_login = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == payload["email"]
    assert "vegili_session" in client.cookies

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert "vegili_session" not in client.cookies


def test_expired_otp_is_rejected(monkeypatch):
    enable_test_otp(monkeypatch)
    payload = register_payload()
    registered = client.post("/api/auth/register", json=payload)
    assert registered.status_code == 200

    email = payload["email"].lower()
    with main.SessionLocal() as db:
        otp = db.get(main.OTPRecord, email)
        otp.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    response = client.post(
        "/api/auth/verify",
        json={"email": payload["email"], "code": registered.json()["dev_code"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Code expired or not found. Register again."



def test_registration_resend_is_throttled(monkeypatch):
    enable_test_otp(monkeypatch)
    payload = register_payload()
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 200

    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 429
    assert second.json()["detail"] == "Please wait before requesting another verification code"



def test_login_rate_limit_returns_retry_after():
    client.cookies.clear()
    # Isolate this test from other login attempts sharing the test database.
    bucket = hashlib.sha256(b"login:testclient").hexdigest()
    with main.SessionLocal() as db:
        db.query(main.RateLimitEvent).filter(
            main.RateLimitEvent.bucket == bucket
        ).delete(synchronize_session=False)
        db.commit()

    payload = register_payload()
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "wrong-password"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "900"
    assert limited.json()["detail"] == "Too many requests. Please try again later."



def test_cross_origin_write_is_rejected():
    response = client.post(
        "/api/auth/logout",
        json={},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.text == "Cross-origin request blocked"



def test_password_change_requires_current_password_and_updates_credentials():
    client.cookies.clear()
    payload = register_payload()
    user = main.User(
        name=payload["name"],
        email=payload["email"],
        password_hash=main.pwd.hash(payload["password"]),
        vegili_id="VGL-PW-" + secrets.token_hex(4).upper(),
        verified=True,
    )
    with main.SessionLocal() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    client.cookies.set("vegili_session", main.serializer.dumps({"uid": user_id}))
    rejected = client.patch(
        "/api/settings/password",
        json={"current_password": "incorrect-password", "new_password": "new-safe-password"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "Current password is incorrect"

    changed = client.patch(
        "/api/settings/password",
        json={"current_password": payload["password"], "new_password": "new-safe-password"},
    )
    assert changed.status_code == 200
    assert changed.json() == {"ok": True}

    client.cookies.clear()
    # Clear the shared login throttle bucket so this test checks the password,
    # not accumulated failed-login attempts from earlier tests.
    bucket = hashlib.sha256(b"login:testclient").hexdigest()
    with main.SessionLocal() as db:
        db.query(main.RateLimitEvent).filter(
            main.RateLimitEvent.bucket == bucket
        ).delete(synchronize_session=False)
        db.commit()

    old_login = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "new-safe-password"},
    )
    assert new_login.status_code == 200
    client.cookies.clear()


def test_password_change_rejects_missing_session():
    client.cookies.clear()
    response = client.patch(
        "/api/settings/password",
        json={"current_password": "old-password", "new_password": "new-password-123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in"
