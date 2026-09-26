import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect


def test_initial_migration_creates_expected_schema(tmp_path):
    database_path = tmp_path / "migration-test.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env["SECRET_KEY"] = "migration-test-secret"
    env["VEGILI_SKIP_CREATE_ALL"] = "true"

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) >= {
            "alembic_version",
            "users",
            "posts",
            "likes",
            "comments",
            "contacts",
            "messages",
        }
        assert inspector.get_columns("users")[1]["name"] == "vegili_id"
        assert {index["name"] for index in inspector.get_indexes("messages")} == {
            "ix_messages_sender_id",
            "ix_messages_receiver_id",
        }
    finally:
        engine.dispose()
