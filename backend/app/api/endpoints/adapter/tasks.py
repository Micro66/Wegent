# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

import io
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, with_task_telemetry
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.schemas.remote_workspace import (
    RemoteWorkspaceStatusResponse,
    RemoteWorkspaceTreeResponse,
)
from app.schemas.service import (
    ServiceDeleteRequest,
    ServiceResponse,
    ServiceUpdate,
)
from app.schemas.shared_task import (
    JoinSharedTaskRequest,
    JoinSharedTaskResponse,
    PublicSharedTaskResponse,
    TaskShareInfo,
    TaskShareResponse,
)
from app.schemas.task import (
    PipelineStageInfo,
    TaskCreate,
    TaskDetail,
    TaskInDB,
    TaskListResponse,
    TaskLiteListResponse,
    TaskSkillsResponse,
    TaskUpdate,
)
from app.services.adapters.task_kinds import task_kinds_service
from app.services.chat.stream_tracker import StreamInfo, stream_tracker
from app.services.remote_workspace_service import remote_workspace_service
from app.services.shared_task import shared_task_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=dict)
def create_task_id(
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Create new task with session id and return task_id"""
    return {
        "task_id": task_kinds_service.create_task_id(db=db, user_id=current_user.id)
    }


@router.post("/create", response_model=TaskInDB, status_code=status.HTTP_201_CREATED)
def create_task_with_optional_id(
    task_create: TaskCreate,
    task_id: Optional[int] = None,
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Create new task with optional task_id in parameters"""
    result = task_kinds_service.create_task_or_append(
        db=db, obj_in=task_create, user=current_user, task_id=task_id
    )

    # Record task creation metric (only if telemetry is enabled)
    if settings.OTEL_ENABLED:
        from shared.telemetry.metrics import record_task_created

        record_task_created(
            user_id=str(current_user.id),
            team_id=str(task_create.team_id) if task_create.team_id else None,
        )

    return result


@router.post("/{task_id}", response_model=TaskInDB, status_code=status.HTTP_201_CREATED)
def create_task_with_id(
    task_create: TaskCreate,
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Create new task with specified task_id"""
    return task_kinds_service.create_task_or_append(
        db=db, obj_in=task_create, user=current_user, task_id=task_id
    )


@router.get("", response_model=TaskListResponse)
def get_tasks(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's task list (paginated), excluding DELETE status tasks"""
    skip = (page - 1) * limit
    items, total = task_kinds_service.get_user_tasks_with_pagination(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return {"total": total, "items": items}


@router.get("/lite", response_model=TaskLiteListResponse)
def get_tasks_lite(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's lightweight task list (paginated) for fast loading, excluding DELETE status tasks"""
    skip = (page - 1) * limit
    items, total = task_kinds_service.get_user_tasks_lite(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return {"total": total, "items": items}


@router.get("/lite/group", response_model=TaskLiteListResponse)
def get_group_tasks_lite(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's group chat task list (paginated) for fast loading.
    Returns only group chat tasks sorted by updated_at descending (most recent activity first).
    """
    skip = (page - 1) * limit
    items, total = task_kinds_service.get_user_group_tasks_lite(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return {"total": total, "items": items}


@router.get("/lite/personal", response_model=TaskLiteListResponse)
def get_personal_tasks_lite(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    types: str = Query(
        "online,offline",
        description="Comma-separated task types to include: online (chat), offline (code), flow",
    ),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's personal (non-group-chat) task list (paginated) for fast loading.
    Returns only personal tasks sorted by created_at descending (newest first).

    Types filter:
    - online: chat tasks (task_type != 'code' and not flow)
    - offline: code tasks (task_type == 'code')
    - flow: flow-triggered tasks (labels.type == 'flow')
    """
    skip = (page - 1) * limit
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    items, total = task_kinds_service.get_user_personal_tasks_lite(
        db=db, user_id=current_user.id, skip=skip, limit=limit, types=type_list
    )
    return {"total": total, "items": items}


@router.get("/search", response_model=TaskListResponse)
def search_tasks_by_title(
    title: str = Query(..., min_length=1, description="Search by task title keywords"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Fuzzy search tasks by title for current user (pagination), excluding DELETE status"""
    skip = (page - 1) * limit
    items, total = task_kinds_service.get_user_tasks_by_title_with_pagination(
        db=db, user_id=current_user.id, title=title, skip=skip, limit=limit
    )
    return {"total": total, "items": items}


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get specified task details with related entities"""
    return task_kinds_service.get_task_detail(
        db=db, task_id=task_id, user_id=current_user.id
    )


@router.get(
    "/{task_id}/remote-workspace/status",
    response_model=RemoteWorkspaceStatusResponse,
)
def get_remote_workspace_status(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Get remote workspace connection and availability status for a task."""
    return remote_workspace_service.get_status(
        db=db,
        task_id=task_id,
        user_id=current_user.id,
    )


@router.get(
    "/{task_id}/remote-workspace/tree",
    response_model=RemoteWorkspaceTreeResponse,
)
def get_remote_workspace_tree(
    path: str = Query("/workspace", description="Workspace path to list"),
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """List remote workspace tree under /workspace."""
    return remote_workspace_service.list_tree(
        db=db,
        task_id=task_id,
        user_id=current_user.id,
        path=path,
    )


@router.get("/{task_id}/remote-workspace/file")
def get_remote_workspace_file(
    path: str = Query(..., description="Workspace file path"),
    disposition: str = Query(
        "inline", pattern="^(inline|attachment)$", description="File disposition"
    ),
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Stream remote workspace file for inline preview or attachment download."""
    return remote_workspace_service.stream_file(
        db=db,
        task_id=task_id,
        user_id=current_user.id,
        path=path,
        disposition=disposition,
    )


@router.get("/{task_id}/skills", response_model=TaskSkillsResponse)
def get_task_skills(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user_jwt_apikey_tasktoken),
    db: Session = Depends(get_db),
):
    """Get all skills associated with a task.

    Follows the chain: task → team → bots → ghosts → skills

    Supports multiple authentication methods:
    - JWT Token (standard user authentication)
    - API Key (for executor/service authentication)
    - Task Token (for executor task-based authentication)

    Returns:
        TaskSkillsResponse with task_id, team_id, team_namespace,
        skills list (deduplicated), and preload_skills list.
    """
    return task_kinds_service.get_task_skills(
        db=db, task_id=task_id, user_id=current_user.id
    )


@router.put("/{task_id}", response_model=TaskInDB)
def update_task(
    task_update: TaskUpdate,
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Update task information"""
    return task_kinds_service.update_task(
        db=db, task_id=task_id, obj_in=task_update, user_id=current_user.id
    )


@router.delete("/{task_id}")
def delete_task(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Delete task"""
    task_kinds_service.delete_task(db=db, task_id=task_id, user_id=current_user.id)
    return {"message": "Task deleted successfully"}


@router.post("/{task_id}/cancel")
async def cancel_task(
    background_tasks: BackgroundTasks,
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a running task by calling executor_manager or Chat Shell cancel"""
    return await task_kinds_service.cancel_task(
        db=db,
        task_id=task_id,
        user_id=current_user.id,
        background_task_runner=background_tasks.add_task,
    )


@router.get("/{task_id}/health")
async def get_task_health(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get task health status for real state verification.

    This endpoint checks the actual execution state by verifying:
    - Chat tasks: Active streams in Redis (StreamTracker)
    - Executor tasks (ClaudeCode/Agno/Dify): Container status via ExecutorManager API

    It helps detect "orphaned" tasks where the database shows RUNNING but
    there's no actual execution (no active stream or container).

    Returns:
        Task health information including:
        - status: 'healthy', 'unhealthy', or 'unknown'
        - database_status: Current status in database
        - active_streams: List of active streams with heartbeat info
        - executor_containers_alive: Whether executor containers are running
        - orphaned: True if database shows RUNNING but no active execution
        - stale_duration_seconds: How long the task has been orphaned
        - recommendation: 'none', 'mark_failed', or 'wait'
    """
    from app.models.subtask import Subtask
    from app.services.chat.storage import session_manager
    from app.services.execution.executor_health import (
        check_executor_containers_alive,
        get_subtask_shell_type,
        is_chat_shell,
        is_executor_shell,
    )

    # Get all subtasks for this task
    subtasks = (
        db.query(Subtask)
        .filter(Subtask.task_id == task_id)
        .order_by(Subtask.id.desc())
        .all()
    )

    # Check for running subtasks in database
    running_subtasks = [s for s in subtasks if s.status == "RUNNING"]
    running_subtask_ids = {s.id for s in running_subtasks}

    # Categorize running subtasks by shell type
    chat_subtasks = []
    executor_subtasks = []

    for subtask in running_subtasks:
        shell_type = get_subtask_shell_type(subtask, db)
        if is_chat_shell(shell_type):
            chat_subtasks.append(subtask)
        elif is_executor_shell(shell_type):
            executor_subtasks.append(subtask)

    # Check Chat tasks: Use StreamTracker (Redis-based heartbeat)
    active_streams = await stream_tracker.get_task_active_streams(task_id)

    # Also check session_manager's task streaming status (legacy tracking)
    # This is set when streaming starts and cleared when streaming ends
    session_streaming_status = await session_manager.get_task_streaming_status(task_id)

    has_active_chat_stream = (
        len(active_streams) > 0 or session_streaming_status is not None
    )

    # Check Executor tasks: Query ExecutorManager for container status
    executor_containers_alive = False
    if executor_subtasks:
        executor_containers_alive = await check_executor_containers_alive(
            task_id, executor_subtasks
        )

    # A stream/execution is considered active if either:
    # 1. Chat stream: StreamTracker has records or session_manager has streaming status
    # 2. Executor tasks: Container is alive according to ExecutorManager
    has_active_execution = has_active_chat_stream or executor_containers_alive

    # Determine orphaned status:
    # A task is orphaned if database shows RUNNING but no active execution
    orphaned = len(running_subtasks) > 0 and not has_active_execution

    logger.info(
        f"[TaskHealth] task_id={task_id}, "
        f"running_subtasks={len(running_subtasks)}, "
        f"chat_subtasks={len(chat_subtasks)}, "
        f"executor_subtasks={len(executor_subtasks)}, "
        f"stream_tracker_streams={len(active_streams)}, "
        f"session_streaming={session_streaming_status is not None}, "
        f"executor_alive={executor_containers_alive}, "
        f"orphaned={orphaned}"
    )

    # Calculate stale duration if orphaned
    stale_duration_seconds = None
    if orphaned and running_subtasks:
        # Use the oldest running subtask's updated_at as stale start time
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        def ensure_utc(dt):
            """Ensure datetime is UTC aware.

            Database stores naive datetimes (assumed to be UTC or local time).
            We need to handle both cases correctly.
            """
            if dt.tzinfo is None:
                # Naive datetime - assume it's in local timezone and convert to UTC
                # For MySQL, timestamps are usually stored in the server timezone
                # We'll treat naive datetimes as already being UTC to avoid conversion issues
                return dt.replace(tzinfo=timezone.utc)
            else:
                # Already has timezone - convert to UTC
                return dt.astimezone(timezone.utc)

        oldest_update = min(
            (ensure_utc(s.updated_at) for s in running_subtasks),
            default=now,
        )
        stale_duration_seconds = int((now - oldest_update).total_seconds())

    # Determine status
    if orphaned:
        status = "unhealthy"
        recommendation = "mark_failed"
    elif len(running_subtasks) > 0 and has_active_execution:
        # Database shows RUNNING and there's active execution (stream or container)
        status = "healthy"
        recommendation = "none"
    elif len(running_subtasks) == 0 and not has_active_execution:
        # Task is not running in either DB or execution layer
        status = "healthy"  # Not running is a valid healthy state
        recommendation = "none"
    else:
        # Execution layer has activity but DB doesn't show RUNNING (inconsistent state)
        status = "unknown"
        recommendation = "wait"

    # Build active streams response
    active_streams_response = [
        {
            "subtask_id": s.subtask_id,
            "shell_type": s.shell_type,
            "started_at": s.started_at,
            "last_heartbeat": s.last_heartbeat,
            "heartbeat_age_seconds": s.heartbeat_age_seconds,
            "executor_location": s.executor_location,
        }
        for s in active_streams
    ]

    # Get database status (use the most recent subtask status, or COMPLETED if no subtasks)
    if subtasks:
        # Prioritize RUNNING status if any subtask is running
        database_status = (
            "RUNNING"
            if any(s.status == "RUNNING" for s in subtasks)
            else subtasks[0].status
        )
    else:
        database_status = "COMPLETED"

    return {
        "task_id": task_id,
        "status": status,
        "database_status": database_status,
        "active_streams": active_streams_response,
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


@router.post("/{task_id}/cleanup-orphaned")
async def cleanup_orphaned_task(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Clean up an orphaned task (database shows RUNNING but no active stream).

    This endpoint:
    1. Marks running subtasks as FAILED in database
    2. Cleans up Redis残留数据
    3. Returns the cleanup result

    Returns:
        Cleanup result with affected subtasks
    """
    from app.models.subtask import Subtask
    from app.services.chat.storage.db import db_handler

    # Get running subtasks for this task
    running_subtasks = (
        db.query(Subtask)
        .filter(Subtask.task_id == task_id, Subtask.status == "RUNNING")
        .all()
    )

    if not running_subtasks:
        return {
            "task_id": task_id,
            "cleaned": False,
            "message": "No running subtasks found",
            "affected_subtasks": [],
        }

    # Import session_manager to get cached content from Redis
    from app.services.chat.storage import session_manager

    # Mark each running subtask as FAILED
    affected_subtasks = []
    for subtask in running_subtasks:
        try:
            # Get cached content from session_manager (Redis)
            # This contains the partial streaming content that hasn't been saved to DB yet
            cached_content = await session_manager.get_streaming_content(subtask.id)

            # Preserve existing result (partial content) if available
            existing_result = subtask.result if subtask.result else {}

            # Build result to save
            if isinstance(existing_result, dict):
                # Keep the existing value but mark as interrupted
                result_to_save = existing_result.copy()
            else:
                # If result is not a dict, create a new one
                result_to_save = {
                    "value": str(existing_result) if existing_result else ""
                }

            # If we have cached content from Redis, use it (it may be newer than DB)
            if cached_content:
                result_to_save["value"] = cached_content
                logger.info(
                    f"[CleanupOrphaned] Retrieved cached_content for subtask {subtask.id}, "
                    f"content_length={len(cached_content)}"
                )

            # Mark as interrupted
            result_to_save["interrupted"] = True
            result_to_save["interrupted_reason"] = (
                "Task executor terminated unexpectedly"
            )

            await db_handler.update_subtask_status(
                subtask.id, "FAILED", result=result_to_save
            )
            affected_subtasks.append(
                {
                    "subtask_id": subtask.id,
                    "previous_status": "RUNNING",
                    "new_status": "FAILED",
                }
            )
            logger.info(
                f"[CleanupOrphaned] Marked subtask {subtask.id} as FAILED, "
                f"preserved_result={bool(existing_result)}, has_cached_content={bool(cached_content)}"
            )
        except Exception as e:
            logger.error(
                f"[CleanupOrphaned] Failed to update subtask {subtask.id}: {e}"
            )

    # Clean up Redis残留数据
    try:
        # Clean up StreamTracker data
        active_streams = await stream_tracker.get_task_active_streams(task_id)
        for stream in active_streams:
            await stream_tracker.unregister_stream(task_id, stream.subtask_id)
            logger.info(
                f"[CleanupOrphaned] Unregistered stream: task_id={task_id}, subtask_id={stream.subtask_id}"
            )
    except Exception as e:
        logger.error(f"[CleanupOrphaned] Failed to cleanup Redis: {e}")

    return {
        "task_id": task_id,
        "cleaned": len(affected_subtasks) > 0,
        "message": f"Cleaned up {len(affected_subtasks)} orphaned subtasks",
        "affected_subtasks": affected_subtasks,
    }


@router.get("/{task_id}/pipeline-stage-info", response_model=PipelineStageInfo)
def get_pipeline_stage_info(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get pipeline stage information for a task.

    Returns current stage, total stages, and stage details for pipeline mode teams.
    For non-pipeline teams, returns default values.

    Args:
        task_id: Task ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        PipelineStageInfo with stage details
    """
    return task_kinds_service.get_pipeline_stage_info(
        db=db,
        task_id=task_id,
        user_id=current_user.id,
    )


@router.post("/{task_id}/share", response_model=TaskShareResponse)
def share_task(
    task_id: int,
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a share link for a task.
    The share link allows others to view the task history and copy it to their task list.
    """
    # Validate that the task belongs to the current user
    if not shared_task_service.validate_task_exists(
        db=db, task_id=task_id, user_id=current_user.id
    ):
        raise HTTPException(
            status_code=404, detail="Task not found or you don't have permission"
        )

    return shared_task_service.share_task(
        db=db, task_id=task_id, user_id=current_user.id
    )


@router.get("/share/info", response_model=TaskShareInfo)
def get_task_share_info(
    share_token: str = Query(..., description="Share token from URL"),
    db: Session = Depends(get_db),
):
    """
    Get task share information from share token.
    This endpoint doesn't require authentication, so anyone with the link can view.
    """
    return shared_task_service.get_share_info(db=db, share_token=share_token)


@router.get("/share/public", response_model=PublicSharedTaskResponse)
def get_public_shared_task(
    token: str = Query(..., description="Share token from URL"),
    db: Session = Depends(get_db),
):
    """
    Get public shared task data for read-only viewing.
    This endpoint doesn't require authentication - anyone with the link can view.
    Only returns public data (no sensitive information like team config, bot details, etc.)
    """
    return shared_task_service.get_public_shared_task(db=db, share_token=token)


@router.post("/share/join", response_model=JoinSharedTaskResponse)
def join_shared_task(
    request: JoinSharedTaskRequest,
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Copy a shared task to the current user's task list.
    This creates a new task with all the subtasks (messages) from the shared task.
    """
    from app.models.kind import Kind

    # If team_id is provided, validate it belongs to the user
    if request.team_id:
        user_team = (
            db.query(Kind)
            .filter(
                Kind.kind == "Team",
                Kind.id == request.team_id,
                Kind.is_active == True,
            )
            .first()
        )

        if not user_team:
            raise HTTPException(
                status_code=400,
                detail="Invalid team_id or team does not belong to you",
            )
    else:
        # Get user's first active team if not specified
        user_team = (
            db.query(Kind)
            .filter(
                Kind.user_id == current_user.id,
                Kind.kind == "Team",
                Kind.is_active == True,
            )
            .first()
        )

        if not user_team:
            raise HTTPException(
                status_code=400,
                detail="You need to have at least one team to copy a shared task",
            )

    return shared_task_service.join_shared_task(
        db=db,
        share_token=request.share_token,
        user_id=current_user.id,
        team_id=user_team.id,
        model_id=request.model_id,
        force_override_bot_model=request.force_override_bot_model or False,
        force_override_bot_model_type=request.force_override_bot_model_type,
        git_repo_id=request.git_repo_id,
        git_url=request.git_url,
        git_repo=request.git_repo,
        git_domain=request.git_domain,
        branch_name=request.branch_name,
    )


def sanitize_filename(name: str) -> str:
    """Remove invalid filename characters"""
    # Remove invalid characters
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Replace whitespace with underscore
    safe_name = re.sub(r"\s+", "_", safe_name)
    # Remove consecutive underscores
    safe_name = re.sub(r"_+", "_", safe_name)
    return safe_name.strip("_")[:100]  # Limit length


@router.get("/{task_id}/export/docx", summary="Export task as DOCX")
async def export_task_docx(
    task_id: int,
    message_ids: Optional[str] = Query(
        None,
        description="Comma-separated list of message IDs to export. If not provided, exports all messages.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(security.get_current_user),
):
    """
    Export task conversation history to DOCX format.

    Returns a downloadable DOCX file containing:
    - Task title and metadata
    - All subtask messages (user prompts and AI responses), or filtered by message_ids
    - Formatted markdown content
    - Embedded images and attachment info
    """
    from app.models.task import TaskResource
    from app.services.task_member_service import task_member_service

    # Check if user has access to the task (owner or group chat member)
    if not task_member_service.is_member(db, task_id, current_user.id):
        raise HTTPException(status_code=404, detail="Task not found")

    # Query task without user_id filter since we already validated access
    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active.in_(
                [TaskResource.STATE_ACTIVE, TaskResource.STATE_SUBSCRIPTION]
            ),
        )
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Parse message_ids if provided
    filter_message_ids: Optional[list[int]] = None
    if message_ids:
        try:
            filter_message_ids = [
                int(id.strip()) for id in message_ids.split(",") if id.strip()
            ]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid message_ids format. Must be comma-separated integers.",
            ) from e

    try:
        # Lazy import docx_generator to avoid loading python-docx at startup
        from app.services.export.docx_generator import generate_task_docx

        # Generate DOCX document with optional message filter
        docx_buffer = generate_task_docx(task, db, message_ids=filter_message_ids)

        # Get task title for filename
        task_data = task.json.get("spec", {})
        task_title = (
            task.json.get("metadata", {}).get("name", "")
            or task_data.get("title", "")
            or task_data.get("prompt", "Chat_Export")[:50]
        )

        # Sanitize filename
        safe_filename = sanitize_filename(task_title)
        filename = f"{safe_filename}_{datetime.now().strftime('%Y-%m-%d')}.docx"

        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(docx_buffer.getvalue()),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"Failed to export task {task_id} to DOCX: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate DOCX document")


@router.get("/{task_id}/services", response_model=ServiceResponse)
def get_task_services(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get task services/app configuration.

    Returns the app field from the task JSON containing service information
    like name, host, previewUrl, mysql, etc.
    """
    from app.models.task import TaskResource
    from app.services.task_member_service import task_member_service

    # Check if user has access to the task
    if not task_member_service.is_member(db, task_id, current_user.id):
        raise HTTPException(status_code=404, detail="Task not found")

    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active.in_(
                [TaskResource.STATE_ACTIVE, TaskResource.STATE_SUBSCRIPTION]
            ),
        )
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # App data is stored under status.app
    status_data = task.json.get("status", {}) if task.json else {}
    app_data = status_data.get("app", {}) if status_data else {}
    return {"app": app_data}


@router.post("/{task_id}/services", response_model=ServiceResponse)
def update_task_services(
    service_update: ServiceUpdate,
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update task services/app configuration (partial merge).

    Merges the provided fields with existing app data.
    Only provided non-None fields will be updated.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.task import TaskResource
    from app.services.task_member_service import task_member_service

    # Check if user has access to the task
    if not task_member_service.is_member(db, task_id, current_user.id):
        raise HTTPException(status_code=404, detail="Task not found")

    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active.in_(
                [TaskResource.STATE_ACTIVE, TaskResource.STATE_SUBSCRIPTION]
            ),
        )
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get existing app data or initialize empty dict
    # App data is stored under status.app
    task_json = task.json or {}
    status_data = task_json.get("status", {}) or {}
    app_data = status_data.get("app", {}) or {}

    # Merge only non-None fields from the request
    update_data = service_update.model_dump(exclude_none=True)
    app_data.update(update_data)

    # Update task JSON with new app data under status.app
    status_data["app"] = app_data
    task_json["status"] = status_data
    task.json = task_json
    task.updated_at = datetime.now()
    flag_modified(task, "json")

    db.commit()
    db.refresh(task)

    return {"app": app_data}


@router.delete("/{task_id}/services", response_model=ServiceResponse)
def delete_task_services(
    delete_request: ServiceDeleteRequest,
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete specified fields from task services/app configuration.

    Removes the specified field names from the app object.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.task import TaskResource
    from app.services.task_member_service import task_member_service

    # Check if user has access to the task
    if not task_member_service.is_member(db, task_id, current_user.id):
        raise HTTPException(status_code=404, detail="Task not found")

    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active.in_(
                [TaskResource.STATE_ACTIVE, TaskResource.STATE_SUBSCRIPTION]
            ),
        )
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get existing app data
    # App data is stored under status.app
    task_json = task.json or {}
    status_data = task_json.get("status", {}) or {}
    app_data = status_data.get("app", {}) or {}

    # Remove specified fields
    for field_name in delete_request.fields:
        app_data.pop(field_name, None)

    # Update task JSON under status.app
    status_data["app"] = app_data
    task_json["status"] = status_data
    task.json = task_json
    task.updated_at = datetime.now()
    flag_modified(task, "json")

    db.commit()
    db.refresh(task)

    return {"app": app_data}


@router.post("/{task_id}/preserve-executor")
def set_preserve_executor(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Set preserve executor flag for a task.

    When this flag is set, the executor pod for this task will not be cleaned up
    by the cleanup_stale_executors job even after the task is completed.
    This is useful for important tasks that need to retain their execution environment.

    Only task owner or group chat members can set this flag.
    """
    return task_kinds_service.set_preserve_executor(
        db=db, task_id=task_id, user_id=current_user.id, preserve=True
    )


@router.delete("/{task_id}/preserve-executor")
def cancel_preserve_executor(
    task_id: int = Depends(with_task_telemetry),
    current_user: User = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancel preserve executor flag for a task.

    Removes the preserve flag, allowing the executor pod to be cleaned up
    by the cleanup_stale_executors job when the task expires.

    Only task owner or group chat members can cancel this flag.
    """
    return task_kinds_service.set_preserve_executor(
        db=db, task_id=task_id, user_id=current_user.id, preserve=False
    )
