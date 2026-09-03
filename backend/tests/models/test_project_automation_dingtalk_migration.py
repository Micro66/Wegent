# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Regression coverage for the typed automation event-source backfill."""

import importlib.util
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, inspect, text

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def _load_migration() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "20260903_a4e9c5d027b1_add_dingtalk_automation_bindings.py"
    )
    spec = importlib.util.spec_from_file_location("dingtalk_automation_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_only_updates_existing_loop_items(monkeypatch) -> None:
    migration = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE loop_items ("
                "id VARCHAR(64) PRIMARY KEY, resource_type VARCHAR(24), metadata JSON)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO loop_items (id, resource_type, metadata) "
                "VALUES ('rule', 'automation_rule', '{\"trigger_type\":\"event\"}')"
            )
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()
        assert (
            connection.execute(
                text("SELECT json_extract(metadata, '$.event_source') FROM loop_items")
            ).scalar_one()
            == "issue"
        )
        assert set(inspect(connection).get_table_names()) == {"loop_items"}

        migration.downgrade()
        assert (
            connection.execute(
                text("SELECT json_extract(metadata, '$.event_source') FROM loop_items")
            ).scalar_one()
            is None
        )
        assert set(inspect(connection).get_table_names()) == {"loop_items"}
