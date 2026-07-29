"""user scoped config tables and user_setting

Revision ID: b8e4a2d03f19
Revises: a7d3f1c92e08
Create Date: 2026-07-29 12:00:00.000000

作者: wanghaobo
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e4a2d03f19"
down_revision: str | Sequence[str] | None = "a7d3f1c92e08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_USER_ID = "default"

# system_setting 中需复制到 default 用户 user_setting 的偏好键（双读过渡期保留 system_setting）
_USER_PREFERENCE_KEYS: tuple[str, ...] = (
    "default_video_backend",
    "default_image_backend",
    "default_image_backend_t2i",
    "default_image_backend_i2i",
    "default_text_backend",
    "default_audio_backend",
    "narration_voice",
    "narration_speed",
    "video_generate_audio",
    "text_backend_simple",
    "text_backend_complex",
    "anthropic_api_key",
    "anthropic_base_url",
    "anthropic_model",
    "anthropic_default_haiku_model",
    "anthropic_default_opus_model",
    "anthropic_default_sonnet_model",
    "claude_code_subagent_model",
)


def _table_exists(conn, name: str) -> bool:
    return name in sa.inspect(conn).get_table_names()


def _column_exists(conn, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _index_exists(conn, table: str, index_name: str) -> bool:
    return index_name in {idx["name"] for idx in sa.inspect(conn).get_indexes(table)}


def _unique_constraint_exists(conn, table: str, name: str) -> bool:
    return name in {uc["name"] for uc in sa.inspect(conn).get_unique_constraints(table)}


def _has_name_only_unique(conn, table: str) -> bool:
    return any(list(uc.get("column_names") or []) == ["name"] for uc in sa.inspect(conn).get_unique_constraints(table))


def _primary_key_name(conn, table: str) -> str | None:
    pk = sa.inspect(conn).get_pk_constraint(table) or {}
    return pk.get("name")


def _ensure_default_user(conn) -> None:
    """确保 ``users`` 中存在 default 行，供各表 user_id FK 指向。

    PostgreSQL 强制 FK：存量表加 ``user_id NOT NULL DEFAULT 'default'`` 时，
    若缺少这一行会直接违反外键。SQLite 默认不校验 FK，但补齐同样无害。
    """
    if not _table_exists(conn, "users"):
        return
    if conn.execute(sa.text("SELECT 1 FROM users WHERE id = :uid"), {"uid": DEFAULT_USER_ID}).scalar():
        return
    if conn.execute(sa.text("SELECT 1 FROM users WHERE username = :uname"), {"uname": DEFAULT_USER_ID}).scalar():
        return

    columns = {c["name"] for c in sa.inspect(conn).get_columns("users")}
    cols = ["id", "username"]
    values = [":uid", ":uname"]
    if "role" in columns:
        cols.append("role")
        values.append("'admin'")
    if "is_active" in columns:
        cols.append("is_active")
        values.append("TRUE")
    for ts in ("created_at", "updated_at"):
        if ts in columns:
            cols.append(ts)
            values.append("CURRENT_TIMESTAMP")

    conn.execute(
        sa.text(f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join(values)})"),
        {"uid": DEFAULT_USER_ID, "uname": DEFAULT_USER_ID},
    )


def _drop_stale_alembic_tmp_tables(conn) -> None:
    """清理 SQLite batch_alter 中断留下的 `_alembic_tmp_*` 表，便于幂等重试。"""
    for name in list(sa.inspect(conn).get_table_names()):
        if name.startswith("_alembic_tmp_"):
            op.execute(sa.text(f'DROP TABLE IF EXISTS "{name}"'))


def _add_user_id_column(batch_op, *, fk_name: str, index_name: str) -> None:
    batch_op.add_column(
        sa.Column(
            "user_id",
            sa.String(),
            server_default=DEFAULT_USER_ID,
            nullable=False,
        )
    )
    batch_op.create_foreign_key(fk_name, "users", ["user_id"], ["id"], ondelete="CASCADE")
    batch_op.create_index(index_name, ["user_id"], unique=False)


def _upgrade_assets() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "assets"):
        return
    # 同一 batch 完成加列 + 唯一约束重建，避免两次 batch_alter 中断留下 tmp 表
    needs_user_id = not _column_exists(conn, "assets", "user_id")
    has_old_uq = _unique_constraint_exists(conn, "assets", "uq_asset_type_name")
    has_new_uq = _unique_constraint_exists(conn, "assets", "uq_asset_user_type_name")
    if not needs_user_id and has_new_uq and not has_old_uq:
        return
    with op.batch_alter_table("assets", schema=None) as batch_op:
        if needs_user_id:
            _add_user_id_column(batch_op, fk_name="fk_assets_user_id", index_name="ix_assets_user_id")
        if has_old_uq:
            batch_op.drop_constraint("uq_asset_type_name", type_="unique")
        if not has_new_uq:
            batch_op.create_unique_constraint("uq_asset_user_type_name", ["user_id", "type", "name"])


def _upgrade_provider_credential() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "provider_credential"):
        return
    needs_user_id = not _column_exists(conn, "provider_credential", "user_id")
    has_old_active = _index_exists(conn, "provider_credential", "uq_provider_credential_one_active")
    has_new_active = _index_exists(conn, "provider_credential", "uq_provider_credential_one_active_per_user")
    if not needs_user_id and has_new_active and not has_old_active:
        return
    with op.batch_alter_table("provider_credential", schema=None) as batch_op:
        if needs_user_id:
            _add_user_id_column(
                batch_op, fk_name="fk_provider_credential_user_id", index_name="ix_provider_credential_user_id"
            )
        if has_old_active:
            batch_op.drop_index("uq_provider_credential_one_active")
        if not has_new_active:
            batch_op.create_index(
                "uq_provider_credential_one_active_per_user",
                ["user_id", "provider"],
                unique=True,
                sqlite_where=sa.text("is_active = 1"),
                postgresql_where=sa.text("is_active"),
            )


def _upgrade_provider_config() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "provider_config"):
        return
    needs_user_id = not _column_exists(conn, "provider_config", "user_id")
    has_old_uq = _unique_constraint_exists(conn, "provider_config", "uq_provider_key")
    has_new_uq = _unique_constraint_exists(conn, "provider_config", "uq_provider_user_key")
    if not needs_user_id and has_new_uq and not has_old_uq:
        return
    with op.batch_alter_table("provider_config", schema=None) as batch_op:
        if needs_user_id:
            _add_user_id_column(batch_op, fk_name="fk_provider_config_user_id", index_name="ix_provider_config_user_id")
        if has_old_uq:
            batch_op.drop_constraint("uq_provider_key", type_="unique")
        if not has_new_uq:
            batch_op.create_unique_constraint("uq_provider_user_key", ["user_id", "provider", "key"])


def _upgrade_custom_provider() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "custom_provider"):
        return
    if not _column_exists(conn, "custom_provider", "user_id"):
        with op.batch_alter_table("custom_provider", schema=None) as batch_op:
            _add_user_id_column(batch_op, fk_name="fk_custom_provider_user_id", index_name="ix_custom_provider_user_id")


def _upgrade_api_keys() -> None:
    """复合唯一 (user_id, name)。匿名 UNIQUE(name) 由后续 c1f8b9e4a720 清理。"""
    conn = op.get_bind()
    if not _table_exists(conn, "api_keys"):
        return
    if _unique_constraint_exists(conn, "api_keys", "uq_api_keys_user_name"):
        return

    inspector = sa.inspect(conn)
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        for uc in inspector.get_unique_constraints("api_keys"):
            if list(uc.get("column_names") or []) != ["name"]:
                continue
            name = uc.get("name")
            if name:
                batch_op.drop_constraint(name, type_="unique")
            break
        else:
            for idx in inspector.get_indexes("api_keys"):
                if idx.get("unique") and list(idx.get("column_names") or []) == ["name"]:
                    batch_op.drop_index(idx["name"])
                    break
        batch_op.create_unique_constraint("uq_api_keys_user_name", ["user_id", "name"])


def _upgrade_projects() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "projects"):
        return

    if not _column_exists(conn, "projects", "id"):
        with op.batch_alter_table("projects", schema=None) as batch_op:
            batch_op.add_column(sa.Column("id", sa.String(length=36), nullable=True))

        rows = conn.execute(sa.text("SELECT name FROM projects WHERE id IS NULL")).fetchall()
        for (name,) in rows:
            conn.execute(
                sa.text("UPDATE projects SET id = :id WHERE name = :name"),
                {"id": str(uuid.uuid4()), "name": name},
            )

        if conn.dialect.name == "sqlite":
            with op.batch_alter_table("projects", schema=None) as batch_op:
                batch_op.alter_column("id", existing_type=sa.String(length=36), nullable=False)
                # SQLite batch 会重建表：先去掉 name 上的 PK，再设 id 为 PK
                batch_op.create_primary_key("pk_projects", ["id"])
                batch_op.create_index(batch_op.f("ix_projects_name"), ["name"], unique=False)
                if not _unique_constraint_exists(conn, "projects", "uq_projects_user_name"):
                    batch_op.create_unique_constraint("uq_projects_user_name", ["user_id", "name"])
        else:
            # PostgreSQL 不重建表：必须显式丢弃 name 上的旧 PK，
            # 否则 ADD PRIMARY KEY 触发 "multiple primary keys for table are not allowed"。
            op.alter_column("projects", "id", existing_type=sa.String(length=36), nullable=False)
            old_pk = _primary_key_name(conn, "projects")
            if old_pk:
                op.drop_constraint(old_pk, "projects", type_="primary")
            op.create_primary_key("pk_projects", "projects", ["id"])
            op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=False)
            if not _unique_constraint_exists(conn, "projects", "uq_projects_user_name"):
                op.create_unique_constraint("uq_projects_user_name", "projects", ["user_id", "name"])
    elif not _unique_constraint_exists(conn, "projects", "uq_projects_user_name"):
        with op.batch_alter_table("projects", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_projects_user_name", ["user_id", "name"])


def _upgrade_user_setting() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "user_setting"):
        return

    op.create_table(
        "user_setting",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), server_default=DEFAULT_USER_ID, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_setting_user_key"),
    )
    op.create_index(op.f("ix_user_setting_user_id"), "user_setting", ["user_id"], unique=False)

    if not _table_exists(conn, "system_setting"):
        return

    now = sa.func.now()
    placeholders = ", ".join(f":k{i}" for i in range(len(_USER_PREFERENCE_KEYS)))
    params = {f"k{i}": key for i, key in enumerate(_USER_PREFERENCE_KEYS)}
    rows = conn.execute(
        sa.text(f"SELECT key, value FROM system_setting WHERE key IN ({placeholders})"),
        params,
    ).fetchall()

    setting_table = sa.table(
        "user_setting",
        sa.column("user_id", sa.String),
        sa.column("key", sa.String),
        sa.column("value", sa.Text),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    for key, value in rows:
        conn.execute(
            setting_table.insert().values(
                user_id=DEFAULT_USER_ID,
                key=key,
                value=value,
                created_at=now,
                updated_at=now,
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    _drop_stale_alembic_tmp_tables(conn)
    _ensure_default_user(conn)
    _upgrade_assets()
    _upgrade_provider_credential()
    _upgrade_provider_config()
    _upgrade_custom_provider()
    _upgrade_api_keys()
    _upgrade_projects()
    _upgrade_user_setting()


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "user_setting"):
        op.drop_index(op.f("ix_user_setting_user_id"), table_name="user_setting")
        op.drop_table("user_setting")

    if _table_exists(conn, "projects") and _column_exists(conn, "projects", "id"):
        if conn.dialect.name == "sqlite":
            with op.batch_alter_table("projects", schema=None) as batch_op:
                if _unique_constraint_exists(conn, "projects", "uq_projects_user_name"):
                    batch_op.drop_constraint("uq_projects_user_name", type_="unique")
                batch_op.drop_index(batch_op.f("ix_projects_name"))
                batch_op.drop_constraint("pk_projects", type_="primary")
                batch_op.create_primary_key("pk_projects", ["name"])
                batch_op.drop_column("id")
        else:
            if _unique_constraint_exists(conn, "projects", "uq_projects_user_name"):
                op.drop_constraint("uq_projects_user_name", "projects", type_="unique")
            op.drop_index(op.f("ix_projects_name"), table_name="projects")
            old_pk = _primary_key_name(conn, "projects")
            if old_pk:
                op.drop_constraint(old_pk, "projects", type_="primary")
            op.create_primary_key("pk_projects", "projects", ["name"])
            op.drop_column("projects", "id")

    if _table_exists(conn, "api_keys"):
        with op.batch_alter_table("api_keys", schema=None) as batch_op:
            if _unique_constraint_exists(conn, "api_keys", "uq_api_keys_user_name"):
                batch_op.drop_constraint("uq_api_keys_user_name", type_="unique")
            # c1f8b9e4a720 的 downgrade 可能已重建 name 全局唯一；具名 + 幂等避免重复约束，
            # 且不能传 None（未配 naming_convention 时 PG 会拒绝匿名约束）。
            if not _has_name_only_unique(conn, "api_keys"):
                batch_op.create_unique_constraint("uq_api_keys_name", ["name"])

    if _table_exists(conn, "custom_provider") and _column_exists(conn, "custom_provider", "user_id"):
        with op.batch_alter_table("custom_provider", schema=None) as batch_op:
            batch_op.drop_constraint("fk_custom_provider_user_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_custom_provider_user_id"))
            batch_op.drop_column("user_id")

    if _table_exists(conn, "provider_config") and _column_exists(conn, "provider_config", "user_id"):
        with op.batch_alter_table("provider_config", schema=None) as batch_op:
            if _unique_constraint_exists(conn, "provider_config", "uq_provider_user_key"):
                batch_op.drop_constraint("uq_provider_user_key", type_="unique")
            batch_op.create_unique_constraint("uq_provider_key", ["provider", "key"])
            batch_op.drop_constraint("fk_provider_config_user_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_provider_config_user_id"))
            batch_op.drop_column("user_id")

    if _table_exists(conn, "provider_credential") and _column_exists(conn, "provider_credential", "user_id"):
        with op.batch_alter_table("provider_credential", schema=None) as batch_op:
            if _index_exists(conn, "provider_credential", "uq_provider_credential_one_active_per_user"):
                batch_op.drop_index("uq_provider_credential_one_active_per_user")
            batch_op.create_index(
                "uq_provider_credential_one_active",
                ["provider"],
                unique=True,
                sqlite_where=sa.text("is_active = 1"),
                postgresql_where=sa.text("is_active"),
            )
            batch_op.drop_constraint("fk_provider_credential_user_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_provider_credential_user_id"))
            batch_op.drop_column("user_id")

    if _table_exists(conn, "assets") and _column_exists(conn, "assets", "user_id"):
        with op.batch_alter_table("assets", schema=None) as batch_op:
            if _unique_constraint_exists(conn, "assets", "uq_asset_user_type_name"):
                batch_op.drop_constraint("uq_asset_user_type_name", type_="unique")
            batch_op.create_unique_constraint("uq_asset_type_name", ["type", "name"])
            batch_op.drop_constraint("fk_assets_user_id", type_="foreignkey")
            batch_op.drop_index(batch_op.f("ix_assets_user_id"))
            batch_op.drop_column("user_id")
