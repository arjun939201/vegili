import os
import tempfile

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app, SessionLocal, User, Post, serializer

client = TestClient(app)


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
        posts = [Post(user_id=user_id, body=f"page-item-{i}") for i in range(3)]
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
    second = client.get(f"/api/feed?limit=2&before_id={data['next_before_id']}")
    assert second.status_code == 200
    assert len(second.json()["posts"]) == 1
    assert second.json()["has_more"] is False
    assert set(p["id"] for p in data["posts"]).isdisjoint(
        p["id"] for p in second.json()["posts"]
    )
    client.cookies.clear()


def test_feed_rejects_out_of_range_page_size():
    response = client.get("/api/feed?limit=101")
    assert response.status_code == 422
