"""OAuth identity linkage for federated login (e.g. Google).

作者: wanghaobo
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class OAuthIdentity(TimestampMixin, Base):
    """Maps an external IdP subject to a local ``users`` row."""

    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
