"""Add OTP issuance timestamp for persisted resend throttling."""
from alembic import op
import sqlalchemy as sa

revision = "0003_otp_throttle"
down_revision = "0002_otp_records"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "otp_records",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE otp_records SET created_at = expires_at")
    with op.batch_alter_table("otp_records") as batch_op:
        batch_op.alter_column("created_at", nullable=False)

def downgrade():
    op.drop_column("otp_records", "created_at")
