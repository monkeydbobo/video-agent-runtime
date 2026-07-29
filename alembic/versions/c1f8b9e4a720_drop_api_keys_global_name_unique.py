"""drop api_keys global name unique

Revision ID: c1f8b9e4a720
Revises: b8e4a2d03f19
Create Date: 2026-07-29 14:00:00.000000

作者: wanghaobo

b8e4a2d03f19 在 SQLite 上未能丢掉匿名 UNIQUE(name)（inspector 返回 name=None），
导致不同用户无法创建同名 API Key。本迁移幂等移除仅含 name 列的唯一约束。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1f8b9e4a720"
down_revision: str | Sequence[str] | None = "b8e4a2d03f19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_name_only_unique(conn) -> bool:
    if "api_keys" not in sa.inspect(conn).get_table_names():
        return False
    return any(
        list(uc.get("column_names") or []) == ["name"] for uc in sa.inspect(conn).get_unique_constraints("api_keys")
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_name_only_unique(conn):
        return

    dialect = conn.dialect.name
    if dialect == "sqlite":
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))
        op.execute(
            sa.text(
                """
                CREATE TABLE api_keys_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    key_hash VARCHAR NOT NULL,
                    key_prefix VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME,
                    last_used_at DATETIME,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    user_id VARCHAR DEFAULT 'default' NOT NULL,
                    CONSTRAINT fk_api_keys_user_id FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                    CONSTRAINT uq_api_keys_user_name UNIQUE (user_id, name),
                    UNIQUE (key_hash)
                )
                """
            )
        )
        op.execute(
            sa.text(
                """
                INSERT INTO api_keys_new (
                    id, name, key_hash, key_prefix, created_at, expires_at,
                    last_used_at, updated_at, user_id
                )
                SELECT
                    id, name, key_hash, key_prefix, created_at, expires_at,
                    last_used_at, updated_at, user_id
                FROM api_keys
                """
            )
        )
        op.execute(sa.text("DROP TABLE api_keys"))
        op.execute(sa.text("ALTER TABLE api_keys_new RENAME TO api_keys"))
        op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id)"))
        op.execute(sa.text("PRAGMA foreign_keys=ON"))
        return

    # PostgreSQL / 其他：按列匹配丢弃 name 全局唯一
    for uc in sa.inspect(conn).get_unique_constraints("api_keys"):
        if list(uc.get("column_names") or []) == ["name"] and uc.get("name"):
            with op.batch_alter_table("api_keys", schema=None) as batch_op:
                batch_op.drop_constraint(uc["name"], type_="unique")
            break


def downgrade() -> None:
    conn = op.get_bind()
    if "api_keys" not in sa.inspect(conn).get_table_names():
        return
    if _has_name_only_unique(conn):
        return
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.create_unique_constraint("uq_api_keys_name", ["name"])
