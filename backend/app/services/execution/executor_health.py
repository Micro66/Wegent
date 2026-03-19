# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Executor health check for container-based tasks.

This module provides health checking for Executor tasks (ClaudeCode, Agno, Dify)
by querying ExecutorManager's container status via HTTP API.

Key Design:
- Chat tasks: Use StreamTracker (Redis-based heartbeat)
- Executor tasks: Query ExecutorManager for container status
"""

import logging
from typing import Any, List

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.kind import Kind
from app.models.subtask import Subtask
from app.schemas.kind import Bot
from app.services.chat.config.shell_checker import get_shell_type

logger = logging.getLogger(__name__)

# Executor shell types that run in containers
EXECUTOR_SHELL_TYPES = {"ClaudeCode", "Agno", "Dify"}


async def check_executor_container_alive(executor_name: str) -> dict:
    """
    Check if executor container is alive via ExecutorManager API.

    Calls EM's /executor-manager/executor/address endpoint.

    Args:
        executor_name: Executor container name

    Returns:
        Dict with alive status and details
    """
    executor_manager_url = settings.EXECUTOR_MANAGER_URL

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{executor_manager_url}/executor-manager/executor/address",
                params={"executor_name": executor_name},
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                # If address is returned, container exists and is running
                return {
                    "alive": True,
                    "exists": data.get("exists", False),
                    "status": data.get("status", "unknown"),
                    "address": data.get("address"),
                }
            elif response.status_code == 404:
                # Container not found
                return {"alive": False, "exists": False, "status": "not_found"}
            else:
                return {
                    "alive": False,
                    "exists": False,
                    "status": f"error_{response.status_code}",
                }

    except httpx.TimeoutException:
        logger.warning(f"[ExecutorHealth] Timeout checking executor {executor_name}")
        return {"alive": False, "exists": False, "status": "timeout"}
    except Exception as e:
        logger.warning(
            f"[ExecutorHealth] Failed to check executor {executor_name}: {e}"
        )
        return {"alive": False, "exists": False, "status": "error"}


async def get_running_executor_containers() -> list[dict[str, Any]]:
    """Fetch the ExecutorManager runtime snapshot."""
    executor_manager_url = settings.EXECUTOR_MANAGER_URL

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{executor_manager_url}/executor-manager/executor/load",
                timeout=5.0,
            )

        if response.status_code != 200:
            logger.warning(
                "[ExecutorHealth] Unexpected executor/load status: %s",
                response.status_code,
            )
            return []

        payload = response.json()
        containers = payload.get("containers", [])
        return containers if isinstance(containers, list) else []
    except httpx.TimeoutException:
        logger.warning("[ExecutorHealth] Timeout fetching executor runtime snapshot")
        return []
    except Exception as e:
        logger.warning(
            "[ExecutorHealth] Failed to fetch executor runtime snapshot: %s", e
        )
        return []


async def check_executor_containers_alive(
    task_id: int, subtasks: List[Subtask]
) -> bool:
    """
    Check if any executor containers are alive for the given subtasks.

    Args:
        task_id: Task ID
        subtasks: List of subtasks to check

    Returns:
        True if at least one container is alive
    """
    checked_names: set[str] = set()

    for subtask in subtasks:
        executor_name = (subtask.executor_name or "").strip()
        if not executor_name or executor_name in checked_names:
            continue

        checked_names.add(executor_name)
        result = await check_executor_container_alive(executor_name)
        if result["alive"]:
            logger.debug(
                "[ExecutorHealth] Container alive: %s, task_id=%s, subtask_id=%s",
                executor_name,
                task_id,
                subtask.id,
            )
            return True

    containers = await get_running_executor_containers()
    for container in containers:
        if str(container.get("task_id")) != str(task_id):
            continue

        logger.debug(
            "[ExecutorHealth] Container alive via executor/load: task_id=%s, container=%s",
            task_id,
            container.get("container_name"),
        )
        return True

    logger.debug(
        "[ExecutorHealth] No alive containers for task_id=%s, checked %s subtasks",
        task_id,
        len(subtasks),
    )
    return False


def get_subtask_shell_type(subtask: Subtask, db: Session) -> str:
    """
    Get shell type for a subtask from its associated bot.

    Args:
        subtask: Subtask object
        db: Database session

    Returns:
        Shell type string (e.g., "Chat", "ClaudeCode", "Agno", "Dify")
    """
    # Get bot_ids from subtask
    bot_ids = subtask.bot_ids
    if not bot_ids:
        return "Chat"  # Default

    # Handle both list and dict formats
    if isinstance(bot_ids, list) and len(bot_ids) > 0:
        first_bot = bot_ids[0]
        if isinstance(first_bot, dict):
            bot_id = first_bot.get("id")
        else:
            bot_id = first_bot
    elif isinstance(bot_ids, dict):
        # If it's a dict, try to get the first value
        values = list(bot_ids.values())
        if values and isinstance(values[0], dict):
            bot_id = values[0].get("id")
        else:
            bot_id = values[0] if values else None
    else:
        bot_id = None

    if not bot_id:
        return "Chat"

    try:
        # Query bot to get shell type
        bot = db.query(Kind).filter(Kind.id == bot_id, Kind.kind == "Bot").first()
        if bot:
            return get_shell_type(db, bot, subtask.user_id) or "Chat"
    except Exception as e:
        logger.warning(
            f"[ExecutorHealth] Failed to get shell type for subtask {subtask.id}: {e}"
        )

    return "Chat"


def is_executor_shell(shell_type: str) -> bool:
    """
    Check if shell type is an executor-based shell.

    Args:
        shell_type: Shell type string

    Returns:
        True if it's ClaudeCode, Agno, or Dify
    """
    return shell_type in EXECUTOR_SHELL_TYPES


def is_chat_shell(shell_type: str) -> bool:
    """
    Check if shell type is a chat-based shell.

    Args:
        shell_type: Shell type string

    Returns:
        True if it's Chat or other non-executor shells
    """
    return not is_executor_shell(shell_type)
