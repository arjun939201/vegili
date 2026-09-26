import os
import tempfile

import pytest

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app, SessionLocal, User, Post, serializer

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_feed_posts():
    """Keep feed tests independent from rows created by other tests."""
    db = SessionLocal()
    try:
        db.query(Post).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_feed_requires_authenticated_user():
    response = client.get("/api/feed")
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in"



def test_feed_cursor_pagination_is_stable():
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Feed Tester",
            email=f"feed-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-FEED-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        from datetime import datetime, timezone
        posts = [Post(user_id=user_id, body=f"page-item-{i}", created_at=datetime(9999, 1, 1, tzinfo=timezone.utc)) for i in range(3)]
        db.add_all(posts)
        db.commit()
    finally:
        db.close()

    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    first = client.get("/api/feed?limit=2")
    assert first.status_code == 200
    data = first.json()
    assert len(data["posts"]) == 2
    assert data["has_more"] is True
    second = client.get(f"/api/feed?limit=2&before_id={data['next_before_id']}&before_created_at={data['next_before_created_at']}")
    assert second.status_code == 200
    assert [p["body"] for p in second.json()["posts"]] == ["page-item-0"]
    assert set(p["id"] for p in data["posts"]).isdisjoint(
        p["id"] for p in second.json()["posts"]
    )
    client.cookies.clear()


def test_feed_rejects_out_of_range_page_size():
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Page Size Tester",
            email=f"pagesize-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-PAGE-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    response = client.get("/api/feed?limit=101")
    assert response.status_code == 422
    client.cookies.clear()



def test_feed_breaks_equal_timestamps_by_descending_post_id():
    from datetime import datetime, timezone
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Feed Tie Tester",
            email=f"feed-tie-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-TIE-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        timestamp = datetime(9998, 1, 1, tzinfo=timezone.utc)
        posts = [
            Post(user_id=user_id, body=f"tie-item-{i}", created_at=timestamp)
            for i in range(3)
        ]
        db.add_all(posts)
        db.commit()
        expected_ids = sorted((p.id for p in posts), reverse=True)
    finally:
        db.close()

    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    response = client.get("/api/feed?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert [p["id"] for p in data["posts"]] == expected_ids[:2]
    assert data["next_before_id"] == expected_ids[1]
    client.cookies.clear()



def test_feed_empty_page_returns_null_cursor():
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Empty Feed Tester",
            email=f"empty-feed-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-EMPTY-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    response = client.get("/api/feed?before_id=1&before_created_at=2026-01-01T00:00:00Z&limit=10")
    assert response.status_code == 200
    assert response.json() == {
        "posts": [],
        "has_more": False,
        "next_before_id": None,
        "next_before_created_at": None,
    }
    client.cookies.clear()



def test_feed_rejects_zero_page_size():
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Zero Page Tester",
            email=f"zero-page-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-ZERO-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    response = client.get("/api/feed?limit=0")
    assert response.status_code == 422
    assert response.json()["detail"] == "limit must be between 1 and 100"
    client.cookies.clear()


def test_feed_cursor_handles_timestamps_out_of_id_order():
    from datetime import datetime, timezone, timedelta
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(
            name="Cursor Order Tester",
            email=f"cursor-order-{token}@example.com",
            password_hash="unused",
            vegili_id=f"VGL-CURSOR-{token}",
            verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        base = datetime(9997, 1, 1, tzinfo=timezone.utc)
        # Deliberately make creation IDs and display chronology disagree.
        posts = [
            Post(user_id=user_id, body="older-high-id", created_at=base),
            Post(user_id=user_id, body="newest-low-id", created_at=base + timedelta(days=2)),
            Post(user_id=user_id, body="middle-mid-id", created_at=base + timedelta(days=1)),
        ]
        db.add_all(posts)
        db.commit()
    finally:
        db.close()

    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    first = client.get("/api/feed?limit=2")
    assert [p["body"] for p in first.json()["posts"]][:2] == ["newest-low-id", "middle-mid-id"]
    cursor_id = first.json()["next_before_id"]
    cursor_time = first.json()["next_before_created_at"]
    second = client.get(
        f"/api/feed?limit=2&before_id={cursor_id}&before_created_at={cursor_time}"
    )
    assert "older-high-id" in [p["body"] for p in second.json()["posts"]]
    client.cookies.clear()


def test_feed_rejects_invalid_timestamp_cursor():
    import secrets

    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        user = User(name="Invalid Cursor Tester", email=f"invalid-cursor-{token}@example.com", password_hash="unused", vegili_id=f"VGL-INVALID-{token}", verified=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))
    response = client.get("/api/feed?before_id=10&before_created_at=not-a-timestamp")
    assert response.status_code == 422
    # Composite cursors must be supplied as a pair to avoid ambiguous pagination.
    assert client.get("/api/feed?before_id=10").status_code == 422
    assert client.get("/api/feed?before_created_at=2026-01-01T00:00:00Z").status_code == 422
    client.cookies.clear()
