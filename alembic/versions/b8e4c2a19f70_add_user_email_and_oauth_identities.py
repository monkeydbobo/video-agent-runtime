"""add user email and oauth_identities

Revision ID: b8e4c2a19f70
Revises: a7d3f1c92e08
Create Date: 2026-07-29 04:00:00.000000

作者: wanghaobo
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e4c2a19f70"
down_revision: str | Sequence[str] | None = "f6a9c4d21b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])

    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("email")
