"""add agent sandbox id

Revision ID: 7d31e2b4a9c0
Revises: a3f1c9b27e54
Create Date: 2026-07-22 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d31e2b4a9c0"
down_revision: str | Sequence[str] | None = "a3f1c9b27e54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sandbox_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_sessions", schema=None) as batch_op:
        batch_op.drop_column("sandbox_id")
