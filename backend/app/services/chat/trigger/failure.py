# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Helpers for failures that happen before execution dispatch starts."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.api.ws.chat_namespace import ChatNamespace

logger = logging.getLogger(__name__)


class _NoopEmitter:
    """Emitter used when only status updates are needed."""

    async def emit(self, event) -> None:
        return None

    async def emit_start(
        self,
        task_id: int,
        subtask_id: int,
        message_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        return None

    async def emit_chunk(
        self,
        task_id: int,
        subtask_id: int,
        content: str,
        offset: int,
        **kwargs,
    ) -> None:
        return None

    async def emit_done(
        self,
        task_id: int,
        subtask_id: int,
        result: Optional[dict] = None,
        **kwargs,
    ) -> None:
        return None

    async def emit_error(
        self,
        task_id: int,
        subtask_id: int,
        error: str,
        **kwargs,
    ) -> None:
        return None

    async def emit_cancelled(
        self,
        task_id: int,
        subtask_id: int,
        **kwargs,
    ) -> None:
        return None

    async def close(self) -> None:
        return None


class _WebSocketErrorEmitter:
    """Emit a chat:error event when WebSocket chat fails before dispatch."""

    def __init__(self, namespace: "ChatNamespace", task_room: str):
        self._namespace = namespace
        self._task_room = task_room

    async def emit(self, event) -> None:
        return None

    async def emit_start(
        self,
        task_id: int,
        subtask_id: int,
        message_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        return None

    async def emit_chunk(
        self,
        task_id: int,
        subtask_id: int,
        content: str,
        offset: int,
        **kwargs,
    ) -> None:
        return None

    async def emit_done(
        self,
        task_id: int,
        subtask_id: int,
        result: Optional[dict] = None,
        **kwargs,
    ) -> None:
        return None

    async def emit_error(
        self,
        task_id: int,
        subtask_id: int,
        error: str,
        **kwargs,
    ) -> None:
        from app.api.ws.events import ChatErrorPayload, ServerEvents

        await self._namespace.emit(
            ServerEvents.CHAT_ERROR,
            ChatErrorPayload(subtask_id=subtask_id, error=error).model_dump(),
            room=self._task_room,
        )

    async def emit_cancelled(
        self,
        task_id: int,
        subtask_id: int,
        **kwargs,
    ) -> None:
        return None

    async def close(self) -> None:
        return None


def fail_task_before_dispatch_sync(
    task_id: int,
    subtask_id: int,
    error_message: str,
    db: Optional["Session"] = None,
) -> None:
    """Synchronously fail a task/subtask that never reached the dispatcher."""
    if db is not None:
        from sqlalchemy.orm.attributes import flag_modified

        from app.models.subtask import Subtask, SubtaskStatus
        from app.models.task import TaskResource
        from app.schemas.kind import Task

        subtask = db.get(Subtask, subtask_id)
        if subtask is not None:
            subtask.status = SubtaskStatus.FAILED
            subtask.error_message = error_message
            subtask.completed_at = datetime.now()
            subtask.updated_at = datetime.now()

        task = (
            db.query(TaskResource)
            .filter(
                TaskResource.id == task_id,
                TaskResource.kind == "Task",
                TaskResource.is_active.in_(TaskResource.is_active_query()),
            )
            .first()
        )
        if task and task.json:
            task_crd = Task.model_validate(task.json)
            if task_crd.status:
                task_crd.status.status = "FAILED"
                task_crd.status.errorMessage = error_message
                task_crd.status.updatedAt = datetime.now()
                task_crd.status.completedAt = datetime.now()
                task.json = task_crd.model_dump(mode="json")
                task.updated_at = datetime.now()
                flag_modified(task, "json")

        db.commit()
        logger.info(
            "[pre_dispatch_failure] Marked task failed before dispatch using caller db: task_id=%d, subtask_id=%d",
            task_id,
            subtask_id,
        )
        return

    from app.services.chat.storage import db_handler

    try:
        db_handler.update_subtask_status_sync(
            subtask_id=subtask_id,
            status="FAILED",
            error=error_message,
        )
        logger.info(
            "[pre_dispatch_failure] Marked task failed before dispatch: task_id=%d, subtask_id=%d",
            task_id,
            subtask_id,
        )
    except Exception as exc:
        logger.error(
            "[pre_dispatch_failure] Failed to mark task failed before dispatch: "
            "task_id=%d, subtask_id=%d, error=%s",
            task_id,
            subtask_id,
            exc,
            exc_info=True,
        )


async def fail_task_before_dispatch(
    *,
    task_id: int,
    subtask_id: int,
    error_message: str,
    result_emitter: Optional[Any] = None,
    namespace: Optional["ChatNamespace"] = None,
    task_room: Optional[str] = None,
) -> None:
    """Fail a task/subtask and notify the active caller when dispatch never started."""
    from app.services.execution.emitters.status_updating import StatusUpdatingEmitter

    wrapped: Any
    if result_emitter is not None:
        wrapped = result_emitter
    elif namespace is not None and task_room:
        wrapped = _WebSocketErrorEmitter(namespace, task_room)
    else:
        wrapped = _NoopEmitter()

    try:
        emitter = StatusUpdatingEmitter(
            wrapped=wrapped,
            task_id=task_id,
            subtask_id=subtask_id,
        )
        await emitter.emit_error(
            task_id=task_id,
            subtask_id=subtask_id,
            error=error_message,
        )
        logger.info(
            "[pre_dispatch_failure] Failed task before dispatch: task_id=%d, subtask_id=%d",
            task_id,
            subtask_id,
        )
    except Exception as exc:
        logger.error(
            "[pre_dispatch_failure] Failed to emit pre-dispatch error: "
            "task_id=%d, subtask_id=%d, error=%s",
            task_id,
            subtask_id,
            exc,
            exc_info=True,
        )
