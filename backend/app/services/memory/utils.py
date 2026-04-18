# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for memory service."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.subtask import Subtask, SubtaskRole, SubtaskStatus
from app.models.task import TaskResource
from app.models.user import User
from app.services.chat.group_chat_config import get_group_chat_history_window
from app.services.memory.schemas import MemorySearchResult
from shared.telemetry.context.large_data import log_large_string_list
from shared.telemetry.decorators import (
    add_span_event,
    set_span_attribute,
    trace_sync,
)

logger = logging.getLogger(__name__)


def _get_group_chat_history_window_for_task(
    db: Session, task_id: int | None
) -> dict[str, int] | None:
    """Load the configured history window for a group chat task."""
    if task_id is None:
        return None

    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active,
        )
        .first()
    )
    if not task or not isinstance(task.json, dict):
        return None

    return get_group_chat_history_window(task.json)


def _get_subtask_timestamp(subtask: Subtask) -> datetime | None:
    """Return the best available timestamp for a subtask."""
    return (
        getattr(subtask, "created_at", None)
        or getattr(subtask, "completed_at", None)
        or getattr(subtask, "updated_at", None)
    )


def _apply_group_chat_history_window_to_subtasks(
    subtasks: List[Subtask],
    history_window: dict[str, int] | None,
) -> List[Subtask]:
    """Filter group chat subtasks by maxDays and maxMessages."""
    if not history_window:
        return subtasks

    max_days = history_window.get("maxDays")
    max_messages = history_window.get("maxMessages")

    filtered = subtasks
    if max_days and max_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
        filtered = [
            subtask
            for subtask in filtered
            if (timestamp := _get_subtask_timestamp(subtask)) is None
            or (
                timestamp.astimezone(timezone.utc)
                if timestamp.tzinfo
                else timestamp.replace(tzinfo=timezone.utc)
            )
            >= cutoff
        ]

    if max_messages and max_messages > 0:
        history_limit = max(max_messages - 1, 0)
        filtered = filtered[:history_limit]

    return filtered


def _get_sender_name(db: Session, sender_user_id: int | None) -> str:
    """Resolve sender name for group chat formatting."""
    if not sender_user_id:
        return "Unknown"

    sender = db.query(User).filter(User.id == sender_user_id).first()
    if sender and sender.user_name:
        return sender.user_name
    return f"User{sender_user_id}"


def _get_agent_name(db: Session, team_id: int | None) -> str | None:
    """Resolve team name for assistant messages in group chat."""
    if not team_id:
        return None

    team = (
        db.query(Kind)
        .filter(
            Kind.id == team_id,
            Kind.kind == "Team",
            Kind.is_active,
        )
        .first()
    )
    return team.name if team else None


def sanitize_memory_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip internal metadata fields before sending messages to the memory service."""
    sanitized_messages = []
    for message in messages:
        sanitized_messages.append(
            {
                "role": message.get("role", ""),
                "content": message.get("content", ""),
            }
        )
    return sanitized_messages


@trace_sync("memory.utils.inject_memories")
def inject_memories_to_prompt(
    base_prompt: str, memories: List[MemorySearchResult]
) -> str:
    """Inject memory context into system prompt.

    Adds a <memory> block at the beginning of the system prompt containing
    relevant memories from previous conversations.

    Args:
        base_prompt: Original system prompt
        memories: List of relevant memories to inject

    Returns:
        Enhanced system prompt with memory context

    Example:
        <memory>
        The following are relevant memories from previous conversations:

        1. [2025-01-15 14:30:45 CST] User prefers Python over JavaScript for backend tasks
        2. [2025-01-14 09:15:22 CST] Project uses FastAPI framework with SQLAlchemy ORM

        Use this context to provide personalized responses.
        </memory>

        {original_system_prompt}
    """
    # Set span attributes for observability
    set_span_attribute("memory.count", len(memories))

    if not memories:
        add_span_event("memory.inject.empty", {"reason": "no_memories_provided"})
        return base_prompt

    # Set memory IDs (truncated to first 5 for performance)
    memory_ids = [memory.id for memory in memories[:5]]
    log_large_string_list("memory.ids", memory_ids)
    if len(memories) > 5:
        set_span_attribute("memory.ids_truncated", True)

    # Build memory list
    memory_lines = []
    parse_errors = 0
    for idx, memory in enumerate(memories, start=1):
        # Extract created_at from top-level memory object (mem0 reserved field)
        # Note: created_at is managed by mem0 (may use US/Pacific or UTC timezone)
        created_at = memory.created_at if hasattr(memory, "created_at") else None
        if created_at and isinstance(created_at, str):
            try:
                # Parse ISO format and convert to local timezone
                # Input: '2025-01-19T12:30:45.123456+00:00' or '2025-01-19T12:30:45Z'
                # mem0 uses US/Pacific timezone by default, but timestamps should have timezone info
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

                # Convert to local timezone for display
                if dt.tzinfo is not None:
                    # Convert to local timezone
                    dt_local = dt.astimezone()
                else:
                    # If no timezone info, assume it's UTC and convert to local
                    dt_local = dt.replace(tzinfo=timezone.utc).astimezone()

                # Format with local timezone for clarity
                # Output: '2025-01-19 12:30:45 CST' or '2025-01-19 12:30:45 UTC+08:00'
                date_str = dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            except (ValueError, TypeError):
                # If parsing fails, use original string (better than empty)
                date_str = created_at
                parse_errors += 1
        else:
            date_str = ""

        # Format: N. [date] memory_content
        if date_str:
            memory_lines.append(f"{idx}. [{date_str}] {memory.memory}")
        else:
            memory_lines.append(f"{idx}. {memory.memory}")

    # Track date parsing errors if any occurred
    if parse_errors > 0:
        set_span_attribute("memory.date_parse_errors", parse_errors)
        add_span_event(
            "memory.date_parse_errors",
            {"error_count": parse_errors, "total_memories": len(memories)},
        )

    memory_block = (
        "<memory>\n"
        "The following are relevant memories from previous conversations:\n\n"
        + "\n".join(memory_lines)
        + "\n\nUse this context to provide personalized responses.\n"
        "</memory>\n\n"
    )

    # Set output attributes
    set_span_attribute("memory.block_length", len(memory_block))
    add_span_event(
        "memory.inject.success",
        {"memories_injected": len(memories), "block_length": len(memory_block)},
    )

    return memory_block + base_prompt


@trace_sync("memory.utils.format_metadata")
def format_metadata_for_logging(metadata: dict) -> str:
    """Format metadata dict for logging (redact sensitive fields).

    Args:
        metadata: Metadata dict

    Returns:
        Formatted string for logging
    """
    # Set span attributes
    set_span_attribute("metadata.field_count", len(metadata))

    # Keep only important fields for logging
    relevant_fields = ["task_id", "team_id", "project_id", "is_group_chat"]
    filtered = {k: v for k, v in metadata.items() if k in relevant_fields}

    # Track which fields were kept
    set_span_attribute("metadata.filtered_count", len(filtered))
    if filtered:
        log_large_string_list("metadata.filtered_fields", list(filtered.keys()))

    return str(filtered)


@trace_sync("memory.utils.build_context_messages")
def build_context_messages(
    db: Session,
    existing_subtasks: List[Subtask],
    current_message: str,
    current_user: User,
    is_group_chat: bool,
    context_limit: int,
) -> List[Dict[str, str]]:
    """Build context messages for memory storage.

    Collects recent completed messages from history and adds the current message.

    IMPORTANT for group chat memory isolation:
    In group chat scenarios, only messages from the current user should use role="user".
    All other messages (from other users AND AI responses) should use role="assistant".
    This prevents mem0 from incorrectly attributing other users' messages as memories
    belonging to the current user.

    Args:
        db: Database session
        existing_subtasks: List of existing subtasks (sorted by message_id desc)
        current_message: Current user message content
        current_user: Current user sending the message
        is_group_chat: Whether this is a group chat
        context_limit: Maximum number of messages to include (includes current message)

    Returns:
        List of message dicts with role and content, in chronological order

    Example (non-group chat):
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]

    Example (group chat - only current user's messages use role="user"):
        [
            {"role": "assistant", "content": "User[bob]: Hello everyone"},
            {"role": "assistant", "content": "AI: Hi Bob!"},
            {"role": "user", "content": "User[alice]: How are you?"}  # current user
        ]
    """
    # Set span attributes for observability
    set_span_attribute("context.limit", context_limit)
    set_span_attribute("context.is_group_chat", is_group_chat)
    set_span_attribute("context.existing_count", len(existing_subtasks))

    context_messages = []

    # Filter for completed USER and ASSISTANT messages only
    completed_subtasks = [
        st
        for st in existing_subtasks
        if st.status == SubtaskStatus.COMPLETED
        and st.role in (SubtaskRole.USER, SubtaskRole.ASSISTANT)
    ]

    if is_group_chat and completed_subtasks:
        history_window = _get_group_chat_history_window_for_task(
            db, completed_subtasks[0].task_id
        )
        completed_subtasks = _apply_group_chat_history_window_to_subtasks(
            completed_subtasks,
            history_window,
        )

    # Get the last (context_limit - 1) completed messages as history
    history_count = min(context_limit - 1, len(completed_subtasks))
    set_span_attribute("context.history_count", history_count)

    for i in range(history_count):
        subtask = completed_subtasks[i]

        # Extract content based on subtask role
        if subtask.role == SubtaskRole.USER:
            content = subtask.prompt or ""
        else:  # ASSISTANT
            content = ""
            if subtask.result and isinstance(subtask.result, dict):
                content = subtask.result.get("value", "")

        # Skip empty messages
        if not content:
            continue

        # Determine the role for mem0 based on chat type and sender
        role = _determine_message_role(
            db=db,
            subtask=subtask,
            current_user=current_user,
            is_group_chat=is_group_chat,
        )

        # Format content with sender prefix for group chat
        content = _format_message_content(
            db=db,
            subtask=subtask,
            content=content,
            is_group_chat=is_group_chat,
        )

        context_messages.append({"role": role, "content": content})

    # Reverse to maintain chronological order (oldest to newest)
    context_messages.reverse()

    # Add current user message (always role="user" since it's from current user)
    current_content = current_message
    if is_group_chat:
        sender_name = (
            current_user.user_name if current_user.user_name else str(current_user.id)
        )
        if not current_content.startswith(f"User[{sender_name}]:"):
            current_content = f"User[{sender_name}]: {current_content}"

    context_messages.append({"role": "user", "content": current_content})

    # Set output attributes
    set_span_attribute("context.output_count", len(context_messages))
    add_span_event(
        "context.build.success",
        {
            "history_messages": history_count,
            "output_messages": len(context_messages),
            "is_group_chat": is_group_chat,
        },
    )

    return context_messages


def _determine_message_role(
    db: Session,
    subtask: Subtask,
    current_user: User,
    is_group_chat: bool,
) -> str:
    """Determine the role to use for a message in mem0 context.

    For non-group chat: use standard mapping (USER -> "user", ASSISTANT -> "assistant")
    For group chat: only current user's messages use "user", all others use "assistant"

    This prevents mem0 from attributing other users' messages as memories of current user.

    Args:
        db: Database session
        subtask: The subtask containing the message
        current_user: The current user storing memory
        is_group_chat: Whether this is a group chat

    Returns:
        "user" or "assistant" role string for mem0
    """
    if not is_group_chat:
        # Non-group chat: standard role mapping
        return "user" if subtask.role == SubtaskRole.USER else "assistant"

    # Group chat: only current user's messages should be role="user"
    # This ensures mem0 only extracts memories from the current user's messages
    if subtask.role == SubtaskRole.USER and subtask.sender_user_id == current_user.id:
        return "user"

    # All other messages (other users' messages AND AI responses) use "assistant"
    return "assistant"


def _format_message_content(
    db: Session,
    subtask: Subtask,
    content: str,
    is_group_chat: bool,
) -> str:
    """Format message content with appropriate prefix for group chat.

    For non-group chat: return content as-is
    For group chat USER messages: add "User[name]: " prefix
    For group chat ASSISTANT messages: add "AI: " prefix

    Args:
        db: Database session
        subtask: The subtask containing the message
        content: Original message content
        is_group_chat: Whether this is a group chat

    Returns:
        Formatted content string
    """
    if not is_group_chat:
        return content

    if subtask.role == SubtaskRole.USER:
        # Get sender name from database
        sender_name = _get_sender_name(db, subtask.sender_user_id)
        prefix = f"User[{sender_name}]: "
        if not content.startswith(prefix):
            return prefix + content
        return content

    agent_name = _get_agent_name(db, getattr(subtask, "team_id", None))
    if agent_name:
        prefix = f"Agent[{agent_name}]: "
        if not content.startswith(prefix):
            return prefix + content
        return content

    # ASSISTANT messages: fall back to the legacy AI prefix when team name is unavailable
    if not content.startswith("AI: "):
        return f"AI: {content}"
    return content
