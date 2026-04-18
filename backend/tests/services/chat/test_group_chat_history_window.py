# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.subtask import SenderType, Subtask, SubtaskRole, SubtaskStatus
from app.models.user import User
from app.services.memory.utils import build_context_messages


@pytest.mark.unit
class TestGroupChatHistoryWindow:
    def test_build_context_messages_filters_out_messages_older_than_max_days(
        self, monkeypatch
    ):
        """Group chat context should exclude history outside the configured day window."""
        db = MagicMock()
        current_user = User(id=1, user_name="alice")

        monkeypatch.setattr(
            "app.services.memory.utils._get_group_chat_history_window_for_task",
            lambda db, task_id: {"maxDays": 2, "maxMessages": 10},
        )
        monkeypatch.setattr(
            "app.services.memory.utils._get_sender_name",
            lambda db, sender_user_id: "bob",
        )
        monkeypatch.setattr(
            "app.services.memory.utils._get_agent_name",
            lambda db, team_id: "agent-a",
        )

        existing_subtasks = [
            Subtask(
                id=3,
                task_id=77,
                team_id=11,
                message_id=3,
                role=SubtaskRole.ASSISTANT,
                status=SubtaskStatus.COMPLETED,
                result={"value": "Recent reply"},
                sender_type=SenderType.TEAM,
                sender_user_id=0,
                created_at=datetime.now(timezone.utc) - timedelta(hours=6),
            ),
            Subtask(
                id=2,
                task_id=77,
                message_id=2,
                role=SubtaskRole.USER,
                status=SubtaskStatus.COMPLETED,
                prompt="Recent hello",
                sender_type=SenderType.USER,
                sender_user_id=2,
                created_at=datetime.now(timezone.utc) - timedelta(hours=12),
            ),
            Subtask(
                id=1,
                task_id=77,
                message_id=1,
                role=SubtaskRole.USER,
                status=SubtaskStatus.COMPLETED,
                prompt="Old message",
                sender_type=SenderType.USER,
                sender_user_id=2,
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
            ),
        ]

        result = build_context_messages(
            db=db,
            existing_subtasks=existing_subtasks,
            current_message="Current question",
            current_user=current_user,
            is_group_chat=True,
            context_limit=10,
        )

        assert result == [
            {"role": "assistant", "content": "User[bob]: Recent hello"},
            {"role": "assistant", "content": "Agent[agent-a]: Recent reply"},
            {"role": "user", "content": "User[alice]: Current question"},
        ]

    def test_build_context_messages_caps_group_chat_history_by_max_messages(
        self, monkeypatch
    ):
        """Group chat context should keep only the configured maximum message count."""
        db = MagicMock()
        current_user = User(id=1, user_name="alice")

        monkeypatch.setattr(
            "app.services.memory.utils._get_group_chat_history_window_for_task",
            lambda db, task_id: {"maxDays": 30, "maxMessages": 3},
        )
        monkeypatch.setattr(
            "app.services.memory.utils._get_sender_name",
            lambda db, sender_user_id: "bob",
        )
        monkeypatch.setattr(
            "app.services.memory.utils._get_agent_name",
            lambda db, team_id: "agent-a",
        )

        existing_subtasks = [
            Subtask(
                id=4,
                task_id=77,
                team_id=11,
                message_id=4,
                role=SubtaskRole.ASSISTANT,
                status=SubtaskStatus.COMPLETED,
                result={"value": "Most recent reply"},
                sender_type=SenderType.TEAM,
                sender_user_id=0,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            ),
            Subtask(
                id=3,
                task_id=77,
                message_id=3,
                role=SubtaskRole.USER,
                status=SubtaskStatus.COMPLETED,
                prompt="Most recent user message",
                sender_type=SenderType.USER,
                sender_user_id=2,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
            ),
            Subtask(
                id=2,
                task_id=77,
                team_id=11,
                message_id=2,
                role=SubtaskRole.ASSISTANT,
                status=SubtaskStatus.COMPLETED,
                result={"value": "Older reply"},
                sender_type=SenderType.TEAM,
                sender_user_id=0,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            ),
            Subtask(
                id=1,
                task_id=77,
                message_id=1,
                role=SubtaskRole.USER,
                status=SubtaskStatus.COMPLETED,
                prompt="Oldest user message",
                sender_type=SenderType.USER,
                sender_user_id=2,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=11),
            ),
        ]

        result = build_context_messages(
            db=db,
            existing_subtasks=existing_subtasks,
            current_message="Current question",
            current_user=current_user,
            is_group_chat=True,
            context_limit=10,
        )

        assert len(result) == 3
        assert result[0]["content"] == "User[bob]: Most recent user message"
        assert result[1]["content"] == "Agent[agent-a]: Most recent reply"
        assert result[2]["content"] == "User[alice]: Current question"
