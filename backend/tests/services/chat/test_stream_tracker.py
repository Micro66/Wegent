# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.stream_tracker import StreamTracker


def test_get_stale_threshold_seconds_uses_configured_value():
    tracker = StreamTracker("redis://localhost:6379/0")

    with patch(
        "app.services.chat.stream_tracker.settings.STREAM_STALE_THRESHOLD_SECONDS", 45
    ):
        assert tracker._get_stale_threshold_seconds() == 45


@pytest.mark.asyncio
async def test_get_task_active_streams_uses_task_index_without_scan():
    tracker = StreamTracker("redis://localhost:6379/0")
    heartbeat = datetime.now(timezone.utc).timestamp()

    client = AsyncMock()
    client.smembers.return_value = {"11"}
    client.hgetall.return_value = {
        "task_id": "7",
        "subtask_id": "11",
        "shell_type": "Chat",
        "started_at": "2026-03-20T00:00:00+00:00",
        "last_heartbeat": str(heartbeat),
        "executor_location": "chat_shell",
    }
    client.scan_iter.side_effect = AssertionError("scan_iter should not be used")

    with patch.object(tracker, "_get_client", AsyncMock(return_value=client)):
        streams = await tracker.get_task_active_streams(7)

    assert len(streams) == 1
    assert streams[0].task_id == 7
    assert streams[0].subtask_id == 11
    client.smembers.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_all_active_streams_uses_global_zset_without_scan():
    tracker = StreamTracker("redis://localhost:6379/0")
    heartbeat = datetime.now(timezone.utc).timestamp()

    client = AsyncMock()
    client.zrange.return_value = ["7:11"]
    client.hgetall.return_value = {
        "task_id": "7",
        "subtask_id": "11",
        "shell_type": "Chat",
        "started_at": "2026-03-20T00:00:00+00:00",
        "last_heartbeat": str(heartbeat),
        "executor_location": "chat_shell",
    }
    client.scan_iter.side_effect = AssertionError("scan_iter should not be used")

    with patch.object(tracker, "_get_client", AsyncMock(return_value=client)):
        streams = await tracker.get_all_active_streams()

    assert len(streams) == 1
    assert streams[0].task_id == 7
    assert streams[0].subtask_id == 11
    client.zrange.assert_awaited_once_with("active_streams:list", 0, -1)
