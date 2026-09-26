"""Persist email OTP verification records."""
from alembic import op
import sqlalchemy as sa

revision = "0002_otp_records"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "otp_records",
        sa.Column("email", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_otp_records_expires_at", "otp_records", ["expires_at"])

def downgrade():
    op.drop_index("ix_otp_records_expires_at", table_name="otp_records")
    op.drop_table("otp_records")
