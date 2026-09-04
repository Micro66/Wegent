"""Remove automatic retry state from board executions.

Revision ID: a6c4e9b2f017
Revises: e4a7b9c2d1f0
Create Date: 2026-09-04 00:00:00+08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a6c4e9b2f017"
down_revision: Union[str, Sequence[str], None] = "e4a7b9c2d1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("loop_item_executions", "max_retries")
    op.drop_column("loop_item_executions", "retry_attempt")


def downgrade() -> None:
    op.add_column(
        "loop_item_executions",
        sa.Column(
            "retry_attempt",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "loop_item_executions",
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
