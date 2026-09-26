import os
import tempfile
import secrets

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app, Comment, Like, Post, SessionLocal, User, serializer

client = TestClient(app)


def make_users_and_post():
    token = secrets.token_hex(6).upper()
    db = SessionLocal()
    try:
        owner = User(name="Post Owner", email=f"owner-{token}@example.com",
                     password_hash="unused", vegili_id=f"VGL-OWN-{token}", verified=True)
        other = User(name="Other User", email=f"other-{token}@example.com",
                     password_hash="unused", vegili_id=f"VGL-OTH-{token}", verified=True)
        db.add_all([owner, other])
        db.commit()
        db.refresh(owner)
        db.refresh(other)
        post = Post(user_id=owner.id, body="Original post")
        db.add(post)
        db.commit()
        db.refresh(post)
        return owner.id, other.id, post.id
    finally:
        db.close()


def sign_in_as(user_id):
    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))


def test_post_edit_requires_authentication():
    _, _, post_id = make_users_and_post()
    client.cookies.clear()
    response = client.patch(f"/api/posts/{post_id}", json={"body": "Changed"})
    assert response.status_code == 401


def test_post_owner_can_edit_and_non_owner_cannot():
    owner_id, other_id, post_id = make_users_and_post()
    sign_in_as(other_id)
    denied = client.patch(f"/api/posts/{post_id}", json={"body": "Hijacked"})
    assert denied.status_code == 403

    sign_in_as(owner_id)
    updated = client.patch(f"/api/posts/{post_id}", json={"body": "  Updated text  "})
    assert updated.status_code == 200
    assert updated.json() == {"id": post_id, "body": "Updated text"}

    db = SessionLocal()
    try:
        assert db.get(Post, post_id).body == "Updated text"
    finally:
        db.close()
        client.cookies.clear()


def test_post_delete_is_owner_only_and_removes_dependent_rows():
    owner_id, other_id, post_id = make_users_and_post()
    db = SessionLocal()
    try:
        db.add(Like(post_id=post_id, user_id=other_id))
        db.add(Comment(post_id=post_id, user_id=other_id, body="A comment"))
        db.commit()
    finally:
        db.close()

    sign_in_as(other_id)
    denied = client.delete(f"/api/posts/{post_id}")
    assert denied.status_code == 403

    sign_in_as(owner_id)
    deleted = client.delete(f"/api/posts/{post_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}

    db = SessionLocal()
    try:
        assert db.get(Post, post_id) is None
        assert db.query(Like).filter_by(post_id=post_id).count() == 0
        assert db.query(Comment).filter_by(post_id=post_id).count() == 0
    finally:
        db.close()
        client.cookies.clear()


def test_edit_rejects_blank_body_and_missing_post():
    owner_id, _, post_id = make_users_and_post()
    sign_in_as(owner_id)
    blank = client.patch(f"/api/posts/{post_id}", json={"body": "   "})
    missing = client.patch("/api/posts/999999", json={"body": "Still here"})
    assert blank.status_code == 422
    assert missing.status_code == 404
    client.cookies.clear()
