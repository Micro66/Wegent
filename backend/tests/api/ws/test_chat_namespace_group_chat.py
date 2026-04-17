# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.ws.chat_namespace import ChatNamespace


def _build_query(result):
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = result
    return query


def _build_team(team_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=team_id,
        name=name,
        namespace="default",
        user_id=1,
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Team",
            "metadata": {"name": name, "namespace": "default"},
            "spec": {
                "collaborationModel": "sequential",
                "members": [
                    {
                        "botRef": {"name": "bot-a", "namespace": "default"},
                        "role": "worker",
                    }
                ],
            },
        },
    )


def _build_task_resource(task_json: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=77,
        json=task_json,
        kind="Task",
        is_active=True,
    )


def _build_created_task(task_json: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=77,
        json=task_json,
    )


def _build_task_json(is_group_chat: bool = True, team_refs: list[dict] | None = None):
    task_spec = {
        "title": "Group chat task",
        "prompt": "hello",
        "teamRef": {"name": "fallback-agent", "namespace": "default", "id": 7},
        "workspaceRef": {"name": "workspace-77", "namespace": "default"},
        "is_group_chat": is_group_chat,
    }
    if team_refs is not None:
        task_spec["teamRefs"] = team_refs

    return {
        "apiVersion": "agent.wecode.io/v1",
        "kind": "Task",
        "metadata": {
            "name": "task-77",
            "namespace": "default",
            "labels": {
                "type": "online",
                "taskType": "chat",
                "source": "chat_shell",
            },
        },
        "spec": task_spec,
        "status": {
            "status": "PENDING",
            "progress": 0,
            "createdAt": "2026-04-17T00:00:00",
            "updatedAt": "2026-04-17T00:00:00",
        },
    }


@pytest.mark.asyncio
@pytest.mark.unit
class TestChatNamespaceGroupChat:
    async def test_group_chat_send_accepts_selected_team_in_team_refs(
        self, monkeypatch
    ):
        """Existing group chats should trigger AI for an allowed selected team."""
        namespace = ChatNamespace("/chat")
        namespace._check_token_expiry = AsyncMock(return_value=False)
        namespace.get_session = AsyncMock(
            return_value={"user_id": 1, "user_name": "alice", "auth_token": "token"}
        )
        namespace.enter_room = AsyncMock()
        namespace._broadcast_user_message = AsyncMock()

        user = SimpleNamespace(id=1, user_name="alice")
        team = _build_team(11, "agent-a")
        task_json = _build_task_json(
            team_refs=[
                {"name": "agent-a", "namespace": "default", "id": 11},
                {"name": "agent-b", "namespace": "default", "id": 22},
            ]
        )
        existing_task = _build_task_resource(task_json)
        created_task = _build_created_task(task_json)

        db = MagicMock()
        db.query.side_effect = [
            _build_query(user),
            _build_query(team),
            _build_query(existing_task),
        ]
        monkeypatch.setattr("app.api.ws.chat_namespace.SessionLocal", lambda: db)
        monkeypatch.setattr(
            "app.api.ws.chat_namespace.process_context_and_rag",
            AsyncMock(return_value=(None, None)),
        )
        monkeypatch.setattr(
            "app.services.chat.config.is_deep_research_protocol", lambda db, team: False
        )
        create_chat_task = AsyncMock(
            return_value=SimpleNamespace(
                task=created_task,
                user_subtask=SimpleNamespace(id=501, message_id=1),
                assistant_subtask=None,
                ai_triggered=True,
            )
        )
        monkeypatch.setattr("app.services.chat.storage.create_chat_task", create_chat_task)

        payload = {"task_id": 77, "team_id": 11, "message": "hello group"}

        result = await namespace.on_chat_send("sid-1", payload)

        assert result == {"task_id": 77, "subtask_id": 501, "message_id": 1}
        assert create_chat_task.await_args.kwargs["should_trigger_ai"] is True
        assert create_chat_task.await_args.kwargs["team"].id == 11

    async def test_group_chat_send_rejects_team_outside_group_config(
        self, monkeypatch
    ):
        """Existing group chats should reject a selected team outside allowed refs."""
        namespace = ChatNamespace("/chat")
        namespace._check_token_expiry = AsyncMock(return_value=False)
        namespace.get_session = AsyncMock(
            return_value={"user_id": 1, "user_name": "alice", "auth_token": "token"}
        )

        user = SimpleNamespace(id=1, user_name="alice")
        disallowed_team = _build_team(99, "agent-c")
        existing_task = _build_task_resource(
            _build_task_json(
                team_refs=[
                    {"name": "agent-a", "namespace": "default", "id": 11},
                    {"name": "agent-b", "namespace": "default", "id": 22},
                ]
            )
        )

        db = MagicMock()
        db.query.side_effect = [
            _build_query(user),
            _build_query(disallowed_team),
            _build_query(existing_task),
        ]
        monkeypatch.setattr("app.api.ws.chat_namespace.SessionLocal", lambda: db)
        monkeypatch.setattr(
            "app.api.ws.chat_namespace.process_context_and_rag",
            AsyncMock(return_value=(None, None)),
        )
        monkeypatch.setattr(
            "app.services.chat.config.is_deep_research_protocol", lambda db, team: False
        )
        create_chat_task = AsyncMock()
        monkeypatch.setattr("app.services.chat.storage.create_chat_task", create_chat_task)

        payload = {"task_id": 77, "team_id": 99, "message": "hello group"}

        result = await namespace.on_chat_send("sid-1", payload)

        assert result == {
            "error": "Selected agent is not available in this group chat."
        }
        create_chat_task.assert_not_awaited()

    async def test_group_chat_send_accepts_legacy_single_team_config(
        self, monkeypatch
    ):
        """Legacy single-team group chats should still allow their only team."""
        namespace = ChatNamespace("/chat")
        namespace._check_token_expiry = AsyncMock(return_value=False)
        namespace.get_session = AsyncMock(
            return_value={"user_id": 1, "user_name": "alice", "auth_token": "token"}
        )
        namespace.enter_room = AsyncMock()
        namespace._broadcast_user_message = AsyncMock()

        user = SimpleNamespace(id=1, user_name="alice")
        team = _build_team(7, "legacy-agent")
        task_json = _build_task_json(team_refs=None)
        task_json["spec"]["teamRef"] = {
            "name": "legacy-agent",
            "namespace": "default",
            "id": 7,
        }
        existing_task = _build_task_resource(task_json)
        created_task = _build_created_task(task_json)

        db = MagicMock()
        db.query.side_effect = [
            _build_query(user),
            _build_query(team),
            _build_query(existing_task),
        ]
        monkeypatch.setattr("app.api.ws.chat_namespace.SessionLocal", lambda: db)
        monkeypatch.setattr(
            "app.api.ws.chat_namespace.process_context_and_rag",
            AsyncMock(return_value=(None, None)),
        )
        monkeypatch.setattr(
            "app.services.chat.config.is_deep_research_protocol", lambda db, team: False
        )
        create_chat_task = AsyncMock(
            return_value=SimpleNamespace(
                task=created_task,
                user_subtask=SimpleNamespace(id=601, message_id=3),
                assistant_subtask=None,
                ai_triggered=True,
            )
        )
        monkeypatch.setattr("app.services.chat.storage.create_chat_task", create_chat_task)

        payload = {"task_id": 77, "team_id": 7, "message": "legacy hello"}

        result = await namespace.on_chat_send("sid-1", payload)

        assert result == {"task_id": 77, "subtask_id": 601, "message_id": 3}
        assert create_chat_task.await_args.kwargs["should_trigger_ai"] is True
