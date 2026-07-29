"""Scope active task deduplication by user.

Revision ID: f6a9c4d21b73
Revises: c1f8b9e4a720
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a9c4d21b73"
down_revision: str | Sequence[str] | None = "c1f8b9e4a720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = sa.text("status IN ('queued', 'running', 'cancelling')")
_OLD_COLUMNS = [
    "project_name",
    "task_type",
    "resource_id",
    sa.text("COALESCE(script_file, '')"),
    sa.text("COALESCE(resource_type, '')"),
]
_NEW_COLUMNS = ["user_id", *_OLD_COLUMNS]


def _create(columns: list[object]) -> None:
    op.create_index(
        "idx_tasks_dedupe_active",
        "tasks",
        columns,
        unique=True,
        sqlite_where=_ACTIVE,
        postgresql_where=_ACTIVE,
    )


def upgrade() -> None:
    op.drop_index("idx_tasks_dedupe_active", table_name="tasks")
    _create(_NEW_COLUMNS)


def downgrade() -> None:
    op.drop_index("idx_tasks_dedupe_active", table_name="tasks")
    _create(_OLD_COLUMNS)
