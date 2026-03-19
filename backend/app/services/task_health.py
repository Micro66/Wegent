# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Task health snapshot helpers."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.subtask import Subtask
from app.services.chat.storage import session_manager
from app.services.chat.stream_tracker import stream_tracker
from app.services.execution.executor_health import (
    check_executor_containers_alive,
    get_subtask_shell_type,
    is_chat_shell,
    is_executor_shell,
)

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    """Return a UTC-aware datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def get_task_health_snapshot(db: Session, task_id: int) -> dict[str, Any]:
    """Build a task health snapshot from DB state and live execution signals."""
    subtasks = (
        db.query(Subtask)
        .filter(Subtask.task_id == task_id)
        .order_by(Subtask.id.desc())
        .all()
    )
    running_subtasks = [subtask for subtask in subtasks if subtask.status == "RUNNING"]

    chat_subtasks = []
    executor_subtasks = []
    for subtask in running_subtasks:
        shell_type = get_subtask_shell_type(subtask, db)
        if is_chat_shell(shell_type):
            chat_subtasks.append(subtask)
        elif is_executor_shell(shell_type):
            executor_subtasks.append(subtask)

    active_streams = await stream_tracker.get_task_active_streams(task_id)
    session_streaming_status = await session_manager.get_task_streaming_status(task_id)
    has_active_chat_stream = (
        bool(active_streams) or session_streaming_status is not None
    )

    executor_containers_alive = False
    if executor_subtasks:
        executor_containers_alive = await check_executor_containers_alive(
            task_id, executor_subtasks
        )

    has_active_execution = has_active_chat_stream or executor_containers_alive
    orphaned = bool(running_subtasks) and not has_active_execution

    logger.info(
        "[TaskHealth] task_id=%s, running_subtasks=%s, chat_subtasks=%s, "
        "executor_subtasks=%s, stream_tracker_streams=%s, session_streaming=%s, "
        "executor_alive=%s, orphaned=%s",
        task_id,
        len(running_subtasks),
        len(chat_subtasks),
        len(executor_subtasks),
        len(active_streams),
        session_streaming_status is not None,
        executor_containers_alive,
        orphaned,
    )

    stale_duration_seconds = None
    if orphaned and running_subtasks:
        now = datetime.now(timezone.utc)
        oldest_update = min(
            (_ensure_utc(subtask.updated_at) for subtask in running_subtasks),
            default=now,
        )
        stale_duration_seconds = int((now - oldest_update).total_seconds())

    if orphaned:
        status = "unhealthy"
        recommendation = "mark_failed"
    elif running_subtasks and has_active_execution:
        status = "healthy"
        recommendation = "none"
    elif not running_subtasks and not has_active_execution:
        status = "healthy"
        recommendation = "none"
    else:
        status = "unknown"
        recommendation = "wait"

    database_status = "COMPLETED"
    if subtasks:
        database_status = (
            "RUNNING"
            if any(subtask.status == "RUNNING" for subtask in subtasks)
            else subtasks[0].status
        )

    return {
        "task_id": task_id,
        "status": status,
        "database_status": database_status,
        "active_streams": [
            {
                "subtask_id": stream.subtask_id,
                "shell_type": stream.shell_type,
                "started_at": stream.started_at,
                "last_heartbeat": stream.last_heartbeat,
                "heartbeat_age_seconds": stream.heartbeat_age_seconds,
                "executor_location": stream.executor_location,
            }
            for stream in active_streams
        ],
        "running_subtasks_count": len(running_subtasks),
        "chat_subtasks_count": len(chat_subtasks),
        "executor_subtasks_count": len(executor_subtasks),
        "active_streams_count": len(active_streams),
        "session_streaming_active": session_streaming_status is not None,
        "executor_containers_alive": executor_containers_alive,
        "orphaned": orphaned,
        "stale_duration_seconds": stale_duration_seconds,
        "recommendation": recommendation,
    }
