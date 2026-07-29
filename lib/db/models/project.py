"""Project ownership model.

项目文件仍存储在扁平目录（ADR 0021），本表记录 project id / 项目名 → 用户的归属关系，
用于按用户维度隔离项目可见性与操作权限。
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin, UserOwnedMixin


class Project(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
