import os
import tempfile
import secrets

_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.name}"
os.environ["SECRET_KEY"] = "test-only-secret-key"

from fastapi.testclient import TestClient

from app.main import app, Contact, SessionLocal, User, serializer

client = TestClient(app)


def make_users_and_request():
    db = SessionLocal()
    try:
        unique = secrets.token_hex(6).upper()
        requester = User(
            name="Requester",
            email=f"requester-{unique}@example.com",
            password_hash="not-used-in-this-test",
            vegili_id=f"VGL-REQ-{unique}",
            verified=True,
        )
        receiver = User(
            name="Receiver",
            email=f"receiver-{unique}@example.com",
            password_hash="not-used-in-this-test",
            vegili_id=f"VGL-REC-{unique}",
            verified=True,
        )
        db.add_all([requester, receiver])
        db.commit()
        db.refresh(requester)
        db.refresh(receiver)
        contact = Contact(requester_id=requester.id, receiver_id=receiver.id, accepted=False)
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return requester.id, receiver.id, contact.id
    finally:
        db.close()


def sign_in_as(user_id):
    client.cookies.set("vegili_session", serializer.dumps({"uid": user_id}))


def test_contact_acceptance_is_limited_to_recipient():
    requester_id, receiver_id, contact_id = make_users_and_request()
    sign_in_as(requester_id)

    response = client.post(f"/api/contacts/{contact_id}/accept")

    assert response.status_code == 404
    assert response.json()["detail"] == "Request not found"

    sign_in_as(receiver_id)
    response = client.post(f"/api/contacts/{contact_id}/accept")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_history_and_send_require_accepted_contact():
    requester_id, receiver_id, _ = make_users_and_request()
    sign_in_as(requester_id)

    history = client.get(f"/api/messages/{receiver_id}")
    sent = client.post(f"/api/messages/{receiver_id}", json={"body": "Hello"})

    assert history.status_code == 403
    assert sent.status_code == 403
    assert history.json()["detail"] == "You must be connected to chat"
    assert sent.json()["detail"] == "You must be connected to chat"



def test_websocket_rejects_non_string_message_body():
    requester_id, receiver_id, contact_id = make_users_and_request()
    db = SessionLocal()
    try:
        contact = db.get(Contact, contact_id)
        contact.accepted = True
        db.commit()
    finally:
        db.close()

    sign_in_as(requester_id)
    with client.websocket_connect(f"/ws/chat/{receiver_id}") as websocket:
        assert websocket.receive_json() == {"type": "ready"}
        websocket.send_json({"body": ["not", "a", "string"]})
        websocket.send_json({"body": "valid message"})
        received = websocket.receive_json()
        assert received["type"] == "message"
        assert received["body"] == "valid message"
        assert received["sender_id"] == requester_id
