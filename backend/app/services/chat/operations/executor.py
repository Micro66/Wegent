# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Executor service for Chat.

This module provides utilities for interacting with the executor_manager,
including task cancellation and status management.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def call_executor_cancel(task_id: int) -> bool:
    """
    Call executor_manager to cancel a task.

    Args:
        task_id: Task ID to cancel

    Returns:
        bool: True if successful, False otherwise
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.EXECUTOR_CANCEL_TASK_URL,
                json={"task_id": task_id},
                timeout=5.0,
            )
            response.raise_for_status()
            logger.info(
                f"executor_manager responded successfully for task_id={task_id}"
            )
            return True
    except Exception as e:
        logger.error(
            f"executor_manager call failed for task_id={task_id}: {e}",
            exc_info=True,
        )
        return False


async def call_executor_delete(executor_name: str) -> bool:
    """
    Call executor_manager to delete an executor container.

    Args:
        executor_name: Executor name (container name) to delete

    Returns:
        bool: True if successful, False otherwise
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.EXECUTOR_DELETE_TASK_URL,
                json={"executor_name": executor_name},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                f"executor_manager delete responded successfully for executor_name={executor_name}"
            )
            return True
    except Exception as e:
        logger.error(
            f"executor_manager delete call failed for executor_name={executor_name}: {e}",
            exc_info=True,
        )
        return False
