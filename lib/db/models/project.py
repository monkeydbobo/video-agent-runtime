"""Project ownership model.

项目文件仍存储在扁平目录（ADR 0021），本表仅记录项目名 → 用户的归属关系，
用于按用户维度隔离项目可见性与操作权限。
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin, UserOwnedMixin


class Project(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String, primary_key=True)
