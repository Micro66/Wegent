# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.task import TaskResource
from app.models.user import User
from shared.models.db import Subtask, SubtaskRole, SubtaskStatus


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_task(db: Session, user: User, *, status: str = "RUNNING") -> TaskResource:
    task = TaskResource(
        user_id=user.id,
        kind="Task",
        name=f"task-health-{user.id}-{status.lower()}",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Task",
            "metadata": {"name": "task-health", "namespace": "default"},
            "spec": {
                "title": "Task Health",
                "prompt": "Check task health",
                "teamRef": {"name": "team-health", "namespace": "default"},
                "workspaceRef": {"name": "workspace-health", "namespace": "default"},
            },
            "status": {
                "status": status,
                "progress": 0 if status == "RUNNING" else 100,
                "result": None,
                "errorMessage": "",
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
                "completedAt": None,
            },
        },
        is_active=TaskResource.STATE_ACTIVE,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _create_running_subtask(
    db: Session,
    user: User,
    task: TaskResource,
    *,
    executor_name: str = "",
) -> Subtask:
    subtask = Subtask(
        user_id=user.id,
        task_id=task.id,
        team_id=1,
        title="assistant",
        bot_ids=[1],
        role=SubtaskRole.ASSISTANT,
        executor_namespace="default",
        executor_name=executor_name,
        prompt="hello",
        status=SubtaskStatus.RUNNING,
        progress=50,
        message_id=1,
        parent_id=0,
        error_message="",
        completed_at=datetime.now(),
        result={"value": ""},
    )
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask


def test_task_health_endpoint_denies_non_member_access(
    test_client: TestClient,
    test_db: Session,
    test_user: User,
):
    other_user = User(
        user_name="other-user",
        password_hash="hash",
        email="other@example.com",
        is_active=True,
        git_info=None,
    )
    test_db.add(other_user)
    test_db.commit()
    test_db.refresh(other_user)

    task = _create_task(test_db, test_user)
    other_token = create_access_token(data={"sub": other_user.user_name})

    response = test_client.get(
        f"/api/tasks/{task.id}/health",
        headers=_auth_header(other_token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_cleanup_orphaned_endpoint_skips_active_task(
    test_client: TestClient,
    test_db: Session,
    test_user: User,
    test_token: str,
):
    task = _create_task(test_db, test_user)
    subtask = _create_running_subtask(test_db, test_user, task)

    with (
        patch(
            "app.services.chat.storage.session_manager.get_streaming_content",
            new=AsyncMock(return_value="partial"),
        ),
        patch(
            "app.services.chat.storage.db_handler.update_subtask_status",
            new=AsyncMock(),
        ) as mock_update_subtask_status,
        patch(
            "app.services.task_health.stream_tracker.get_task_active_streams",
            new=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        task_id=task.id,
                        subtask_id=subtask.id,
                        shell_type="Chat",
                        started_at=datetime.now().isoformat(),
                        last_heartbeat=datetime.now().timestamp(),
                        heartbeat_age_seconds=1.0,
                        executor_location="chat_shell",
                    )
                ]
            ),
        ),
        patch(
            "app.services.chat.storage.session_manager.get_task_streaming_status",
            new=AsyncMock(return_value={"subtask_id": subtask.id}),
        ),
    ):
        response = test_client.post(
            f"/api/tasks/{task.id}/cleanup-orphaned",
            headers=_auth_header(test_token),
        )

    assert response.status_code == 200
    assert response.json()["cleaned"] is False
    assert response.json()["message"] == "Task is not orphaned"
    mock_update_subtask_status.assert_not_called()


def test_cleanup_orphaned_endpoint_denies_non_member_access(
    test_client: TestClient,
    test_db: Session,
    test_user: User,
):
    other_user = User(
        user_name="cleanup-other-user",
        password_hash="hash",
        email="cleanup-other@example.com",
        is_active=True,
        git_info=None,
    )
    test_db.add(other_user)
    test_db.commit()
    test_db.refresh(other_user)

    task = _create_task(test_db, test_user)
    _create_running_subtask(test_db, test_user, task)
    other_token = create_access_token(data={"sub": other_user.user_name})

    response = test_client.post(
        f"/api/tasks/{task.id}/cleanup-orphaned",
        headers=_auth_header(other_token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_task_health_marks_chat_task_orphaned_when_session_status_missing(
    test_client: TestClient,
    test_db: Session,
    test_user: User,
    test_token: str,
):
    task = _create_task(test_db, test_user)
    subtask = _create_running_subtask(test_db, test_user, task)

    with (
        patch(
            "app.services.task_health.stream_tracker.get_task_active_streams",
            new=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        task_id=task.id,
                        subtask_id=subtask.id,
                        shell_type="Chat",
                        started_at=datetime.now().isoformat(),
                        last_heartbeat=datetime.now().timestamp(),
                        heartbeat_age_seconds=5.0,
                        executor_location="chat_shell",
                    )
                ]
            ),
        ),
        patch(
            "app.services.chat.storage.session_manager.get_task_streaming_status",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = test_client.get(
            f"/api/tasks/{task.id}/health",
            headers=_auth_header(test_token),
        )

    assert response.status_code == 200
    assert response.json()["active_streams_count"] == 1
    assert response.json()["orphaned"] is True
    assert response.json()["recommendation"] == "mark_failed"


def test_task_health_clamps_negative_stale_duration(
    test_client: TestClient,
    test_db: Session,
    test_user: User,
    test_token: str,
):
    task = _create_task(test_db, test_user)
    subtask = _create_running_subtask(test_db, test_user, task)
    subtask.updated_at = datetime.now() + timedelta(hours=8)
    test_db.add(subtask)
    test_db.commit()

    with (
        patch(
            "app.services.task_health.stream_tracker.get_task_active_streams",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.chat.storage.session_manager.get_task_streaming_status",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = test_client.get(
            f"/api/tasks/{task.id}/health",
            headers=_auth_header(test_token),
        )

    assert response.status_code == 200
    assert response.json()["orphaned"] is True
    assert response.json()["stale_duration_seconds"] == 0
