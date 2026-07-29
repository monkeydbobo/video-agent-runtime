"""用户级设置 ORM（从 system_setting 拆出的 per-user 偏好）。

作者: wanghaobo
"""

from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin, UserOwnedMixin


class UserSetting(TimestampMixin, UserOwnedMixin, Base):
    __tablename__ = "user_setting"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_setting_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
