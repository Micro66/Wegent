# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Contracts for removing board execution retry state."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.unit


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "20260904_a6c4e9b2f017_remove_loop_execution_retries.py"
    )
    spec = importlib.util.spec_from_file_location(
        "loop_execution_retry_migration", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_and_downgrade_remove_and_restore_retry_columns() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "loop_item_executions",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="1"),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {
            column["name"]
            for column in sa.inspect(connection).get_columns("loop_item_executions")
        } == {"id"}

        migration.downgrade()
        assert {
            column["name"]
            for column in sa.inspect(connection).get_columns("loop_item_executions")
        } == {"id", "retry_attempt", "max_retries"}

    assert migration.down_revision == "e4a7b9c2d1f0"
