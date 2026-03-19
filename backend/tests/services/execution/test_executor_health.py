# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.execution.executor_health import (
    check_executor_containers_alive,
    is_executor_shell,
)


@pytest.mark.asyncio
async def test_check_executor_containers_alive_uses_subtask_executor_name():
    subtask = SimpleNamespace(id=101, executor_name="wegent-task-user-abc123")

    with patch(
        "app.services.execution.executor_health.check_executor_container_alive",
        new=AsyncMock(return_value={"alive": True}),
    ) as mock_check:
        alive = await check_executor_containers_alive(42, [subtask])

    assert alive is True
    mock_check.assert_awaited_once_with("wegent-task-user-abc123")


def test_is_executor_shell_excludes_dify_external_api():
    assert is_executor_shell("ClaudeCode") is True
    assert is_executor_shell("Agno") is True
    assert is_executor_shell("Dify") is False
