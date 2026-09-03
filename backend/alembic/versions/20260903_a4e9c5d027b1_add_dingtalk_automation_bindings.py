"""Backfill typed project automation event sources.

Revision ID: a4e9c5d027b1
Revises: 8d3d51c83c99
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a4e9c5d027b1"
down_revision: Union[str, Sequence[str], None] = "8d3d51c83c99"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _update_event_source(*, remove: bool) -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("loop_items"):
        return
    dialect = bind.dialect.name
    if dialect == "mysql":
        expression = (
            "JSON_REMOVE(metadata, '$.event_source')"
            if remove
            else "JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.event_source', 'issue')"
        )
    elif dialect == "sqlite":
        expression = (
            "json_remove(metadata, '$.event_source')"
            if remove
            else "json_set(COALESCE(metadata, '{}'), '$.event_source', 'issue')"
        )
    else:
        expression = (
            "metadata - 'event_source'"
            if remove
            else "COALESCE(metadata, '{}'::jsonb) || '{\"event_source\":\"issue\"}'::jsonb"
        )
    bind.execute(
        sa.text(
            f"UPDATE loop_items SET metadata = {expression} "
            "WHERE resource_type = 'automation_rule'"
        )
    )


def upgrade() -> None:
    _update_event_source(remove=False)


def downgrade() -> None:
    _update_event_source(remove=True)
