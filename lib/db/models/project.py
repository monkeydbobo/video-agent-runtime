"""Project ownership model.

本表以不可变 project id 和 ``(user_id, name)`` 记录归属；项目文件存储在
``users/{user_id}/projects/{project_id}``，名称只作为用户作用域内的可读标识。
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin, UserOwnedMixin


class Project(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
