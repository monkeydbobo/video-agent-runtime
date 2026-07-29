"""用户隔离 schema 迁移烟测（SQLite）。

作者: wanghaobo
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration


def _alembic_cfg() -> Config:
    """空构造 + set_main_option，与 ``lib.db.init_db()`` 同一路径。

    传 ``alembic.ini`` 会让 ``env.py`` 执行 ``fileConfig()``，它默认
    ``disable_existing_loggers=True``——会禁掉已建好的 logger，让同进程后续
    断言日志输出的测试静默失败。
    """
    root = Path(__file__).resolve().parents[1]
    cfg = Config()
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def test_user_scope_migration_sqlite(tmp_path: Path, monkeypatch) -> None:
    """从空库升到 head：资产/凭证/配置/项目均带 user_id，api_keys 无全局 name 唯一。"""
    db_path = tmp_path / "mig.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_cfg()
    command.upgrade(cfg, "a7d3f1c92e08")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    assert "user_setting" in insp.get_table_names()

    for table in ("assets", "provider_credential", "provider_config", "custom_provider", "projects"):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "user_id" in cols, table

    project_cols = {c["name"] for c in insp.get_columns("projects")}
    assert "id" in project_cols

    name_only = any(list(uc.get("column_names") or []) == ["name"] for uc in insp.get_unique_constraints("api_keys"))
    assert not name_only
    assert any(
        list(uc.get("column_names") or []) == ["user_id", "name"] for uc in insp.get_unique_constraints("api_keys")
    )

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert ver == "b8e4c2a19f70"


def test_user_scope_migration_downgrade_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """upgrade → 幂等 → downgrade 回本次迁移前 → 再 upgrade 的闭环。

    只覆盖本次新增的两个 revision：更早的链在 SQLite 上 ``downgrade base`` 会撞到
    表达式索引 ``idx_tasks_dedupe_active`` 无法反射的既有缺陷，全链闭环由
    postgres-compat CI job 负责。
    """
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_cfg()
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # 幂等：第二次应为 no-op

    engine = create_engine(f"sqlite:///{db_path}")
    command.downgrade(cfg, "a7d3f1c92e08")
    insp = inspect(engine)
    assert "user_setting" not in insp.get_table_names()
    assert "user_id" not in {c["name"] for c in insp.get_columns("assets")}
    assert "id" not in {c["name"] for c in insp.get_columns("projects")}

    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert "user_setting" in insp.get_table_names()
    assert "user_id" in {c["name"] for c in insp.get_columns("assets")}
    assert not any(list(uc.get("column_names") or []) == ["name"] for uc in insp.get_unique_constraints("api_keys"))
