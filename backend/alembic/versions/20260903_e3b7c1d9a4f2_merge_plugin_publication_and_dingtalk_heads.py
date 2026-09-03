"""Merge plugin publication and DingTalk automation migration heads.

Revision ID: e3b7c1d9a4f2
Revises: c2f8d4a6b901, a4e9c5d027b1
Create Date: 2026-09-03
"""

from typing import Sequence, Union

revision: str = "e3b7c1d9a4f2"
down_revision: Union[str, Sequence[str], None] = (
    "c2f8d4a6b901",
    "a4e9c5d027b1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge Alembic heads without schema changes."""


def downgrade() -> None:
    """No-op downgrade for merge revision."""
