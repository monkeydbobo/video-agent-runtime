"""merge E2B sandbox branch with upstream migrations

Revision ID: c4a91e7d2b60
Revises: 7d31e2b4a9c0, e167b56a3e79
Create Date: 2026-07-23 15:00:00.000000
"""

from collections.abc import Sequence

revision: str = "c4a91e7d2b60"
down_revision: str | Sequence[str] | None = ("7d31e2b4a9c0", "e167b56a3e79")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
