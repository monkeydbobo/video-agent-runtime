"""add password hash to users

Revision ID: 53f6d210c8a4
Revises: c4a91e7d2b60
Create Date: 2026-07-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "53f6d210c8a4"
down_revision: str | Sequence[str] | None = "c4a91e7d2b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_hash")
