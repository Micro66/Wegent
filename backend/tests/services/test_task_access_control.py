# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.task import TaskResource
from app.services.adapters.task_kinds import TaskKindsService
from app.services.task_member_service import TaskMemberService


@pytest.mark.unit
class TestTaskAccessControl:
    """Test task access control in TaskKindsService.get_task_by_id"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def task_service(self):
        """Create TaskKindsService instance"""
        return TaskKindsService(TaskResource)

    @pytest.fixture
    def mock_task(self):
        """Create a mock task"""
        task = Mock(spec=TaskResource)
        task.id = 123
        task.user_id = 1
        task.kind = "Task"
        task.is_active = True
        task.json = {"status": {"status": "RUNNING"}}
        return task

    def test_owner_can_access_task(self, task_service, mock_db, mock_task):
        """Test that task owner can access their task"""
        # Mock database query to return the task
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_task

        # Mock task_member_service.is_member to return True for owner
        with patch(
            "app.services.task_member_service.task_member_service"
        ) as mock_service:
            mock_service.is_member.return_value = True

            # Mock convert_to_task_dict function from converters module
            with patch(
                "app.services.adapters.task_kinds.queries.convert_to_task_dict"
            ) as mock_convert:
                mock_convert.return_value = {"id": 123, "user_id": 1}

                # Owner (user_id=1) tries to access task
                result = task_service.get_task_by_id(mock_db, task_id=123, user_id=1)

                # Should succeed and return task dict
                assert result is not None
                assert result["id"] == 123
                mock_service.is_member.assert_called_once_with(mock_db, 123, 1)

    def test_member_can_access_group_chat(self, task_service, mock_db, mock_task):
        """Test that group chat member can access the task"""
        # Mock database query to return the task
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_task

        # Mock task_member_service.is_member to return True for member
        with patch(
            "app.services.task_member_service.task_member_service"
        ) as mock_service:
            mock_service.is_member.return_value = True

            # Mock convert_to_task_dict function from converters module
            with patch(
                "app.services.adapters.task_kinds.queries.convert_to_task_dict"
            ) as mock_convert:
                mock_convert.return_value = {"id": 123, "user_id": 1}

                # Member (user_id=2) tries to access task
                result = task_service.get_task_by_id(mock_db, task_id=123, user_id=2)

                # Should succeed and return task dict
                assert result is not None
                assert result["id"] == 123
                mock_service.is_member.assert_called_once_with(mock_db, 123, 2)

    def test_non_member_cannot_access_group_chat(
        self, task_service, mock_db, mock_task
    ):
        """Test that non-member cannot access group chat"""
        # Mock database query to return the task
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_task

        # Mock task_member_service.is_member to return False for non-member
        with patch(
            "app.services.task_member_service.task_member_service"
        ) as mock_service:
            mock_service.is_member.return_value = False

            # Non-member (user_id=3) tries to access task
            with pytest.raises(HTTPException) as exc_info:
                task_service.get_task_by_id(mock_db, task_id=123, user_id=3)

            # Should raise 404 error
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Task not found"
            mock_service.is_member.assert_called_once_with(mock_db, 123, 3)

    def test_task_not_found_returns_404(self, task_service, mock_db):
        """Test that non-existent task returns 404"""
        # Mock database query to return None
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        # User tries to access non-existent task
        with pytest.raises(HTTPException) as exc_info:
            task_service.get_task_by_id(mock_db, task_id=999, user_id=1)

        # Should raise 404 error
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Task not found"

    def test_deleted_task_not_accessible(self, task_service, mock_db):
        """Test that deleted tasks are not accessible"""
        # Mock a deleted task
        deleted_task = Mock(spec=TaskResource)
        deleted_task.id = 123
        deleted_task.user_id = 1
        deleted_task.kind = "Task"
        deleted_task.is_active = True
        deleted_task.json = {"status": {"status": "DELETE"}}

        # Mock database query to return None (filtered out by DELETE status)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        # Owner tries to access deleted task
        with pytest.raises(HTTPException) as exc_info:
            task_service.get_task_by_id(mock_db, task_id=123, user_id=1)

        # Should raise 404 error
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Task not found"

    def test_inactive_task_not_accessible(self, task_service, mock_db):
        """Test that inactive tasks are not accessible"""
        # Mock database query to return None (filtered out by is_active=True)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        # Owner tries to access inactive task
        with pytest.raises(HTTPException) as exc_info:
            task_service.get_task_by_id(mock_db, task_id=123, user_id=1)

        # Should raise 404 error
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Task not found"


@pytest.mark.unit
class TestGroupChatConfigUpdates:
    @pytest.fixture
    def mock_db(self):
        return Mock(spec=Session)

    @pytest.fixture
    def task_member_service(self):
        return TaskMemberService()

    @pytest.fixture
    def mock_task(self):
        task = Mock(spec=TaskResource)
        task.id = 123
        task.user_id = 1
        task.kind = "Task"
        task.is_active = True
        task.is_group_chat = False
        task.json = {
            "spec": {
                "title": "Test task",
                "prompt": "hello",
                "teamRef": {
                    "name": "alpha",
                    "namespace": "default",
                    "user_id": 1,
                },
                "is_group_chat": False,
            }
        }
        return task

    def test_convert_to_group_chat_defaults_history_window(
        self, task_member_service, mock_db, mock_task
    ):
        """Converting a task should persist teamRefs and the default history window."""
        with (
            patch.object(task_member_service, "get_task", return_value=mock_task),
            patch("app.services.task_member_service.flag_modified"),
        ):
            converted = task_member_service.convert_to_group_chat(
                mock_db,
                123,
                team_refs=[
                    {"name": "alpha", "namespace": "default", "user_id": 1},
                    {"name": "beta", "namespace": "default", "user_id": 1},
                ],
            )

        assert converted is True
        assert mock_task.json["spec"]["teamRefs"] == [
            {"name": "alpha", "namespace": "default", "user_id": 1},
            {"name": "beta", "namespace": "default", "user_id": 1},
        ]
        assert mock_task.json["spec"]["groupChatConfig"]["historyWindow"] == {
            "maxDays": 2,
            "maxMessages": 200,
        }

    def test_convert_to_group_chat_updates_existing_group_settings(
        self, task_member_service, mock_db, mock_task
    ):
        """Existing group chats should accept settings updates instead of short-circuiting."""
        mock_task.is_group_chat = True
        mock_task.json["spec"]["is_group_chat"] = True
        mock_task.json["spec"]["teamRefs"] = [
            {"name": "alpha", "namespace": "default", "user_id": 1}
        ]
        mock_task.json["spec"]["groupChatConfig"] = {
            "historyWindow": {"maxDays": 2, "maxMessages": 200}
        }

        with (
            patch.object(task_member_service, "get_task", return_value=mock_task),
            patch("app.services.task_member_service.flag_modified"),
        ):
            converted = task_member_service.convert_to_group_chat(
                mock_db,
                123,
                team_refs=[
                    {"name": "beta", "namespace": "default", "user_id": 1},
                    {"name": "gamma", "namespace": "default", "user_id": 1},
                ],
                history_window={"maxDays": 5, "maxMessages": 80},
            )

        assert converted is True
        assert mock_task.json["spec"]["teamRefs"] == [
            {"name": "beta", "namespace": "default", "user_id": 1},
            {"name": "gamma", "namespace": "default", "user_id": 1},
        ]
        assert mock_task.json["spec"]["groupChatConfig"]["historyWindow"] == {
            "maxDays": 5,
            "maxMessages": 80,
        }
