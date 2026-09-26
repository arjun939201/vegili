"""Initial Vegili schema baseline."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("vegili_id", sa.String(24), nullable=False), sa.Column("name", sa.String(80), nullable=False), sa.Column("email", sa.String(255), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("vegili_id"), sa.UniqueConstraint("email"))
    op.create_index("ix_users_vegili_id", "users", ["vegili_id"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("posts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_posts_user_id", "posts", ["user_id"])
    op.create_table("likes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.UniqueConstraint("post_id", "user_id"))
    op.create_table("comments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("body", sa.String(1000), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_comments_post_id", "comments", ["post_id"])
    op.create_table("contacts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("receiver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("requester_id", "receiver_id"))
    op.create_table("messages", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("receiver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("body", sa.String(4000), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_receiver_id", "messages", ["receiver_id"])

def downgrade():
    op.drop_index("ix_messages_receiver_id", table_name="messages")
    op.drop_index("ix_messages_sender_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("contacts")
    op.drop_index("ix_comments_post_id", table_name="comments")
    op.drop_table("comments")
    op.drop_table("likes")
    op.drop_index("ix_posts_user_id", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_vegili_id", table_name="users")
    op.drop_table("users")
