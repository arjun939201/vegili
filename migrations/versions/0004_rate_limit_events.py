"""Create persistent auth rate-limit event table."""
from alembic import op
import sqlalchemy as sa

revision = "0004_rate_limit_events"
down_revision = "0003_otp_throttle"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bucket", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_limit_events_bucket", "rate_limit_events", ["bucket"])
    op.create_index("ix_rate_limit_events_created_at", "rate_limit_events", ["created_at"])

def downgrade():
    op.drop_index("ix_rate_limit_events_created_at", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_bucket", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
