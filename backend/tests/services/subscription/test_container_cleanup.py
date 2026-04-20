# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for subscription task container cleanup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.events import TaskCompletedEvent
from app.schemas.subscription import BackgroundExecutionStatus
from app.services.subscription.task_completion_handler import (
    SubscriptionTaskCompletionHandler,
)


@pytest.fixture
def handler():
    """Create a SubscriptionTaskCompletionHandler instance."""
    return SubscriptionTaskCompletionHandler()


@pytest.fixture
def mock_event_with_executor():
    """Create a TaskCompletedEvent with executor_name."""
    return TaskCompletedEvent(
        task_id=1,
        subtask_id=2,
        user_id=123,
        status="COMPLETED",
        result={"value": "test result"},
        executor_name="test-executor-abc123",
        executor_namespace="default",
    )


@pytest.fixture
def mock_event_without_executor():
    """Create a TaskCompletedEvent without executor_name."""
    return TaskCompletedEvent(
        task_id=1,
        subtask_id=2,
        user_id=123,
        status="COMPLETED",
        result={"value": "test result"},
        executor_name=None,
        executor_namespace=None,
    )


class TestCleanupExecutorContainer:
    """Tests for _cleanup_executor_container method."""

    @pytest.mark.asyncio
    async def test_cleanup_with_executor_name(self, handler, mock_event_with_executor):
        """Test container cleanup when executor_name is provided."""
        with patch(
            "app.services.subscription.task_completion_handler.call_executor_delete",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = True

            await handler._cleanup_executor_container(mock_event_with_executor)

            mock_delete.assert_called_once_with("test-executor-abc123")

    @pytest.mark.asyncio
    async def test_cleanup_without_executor_name(
        self, handler, mock_event_without_executor
    ):
        """Test that cleanup is skipped when executor_name is None."""
        with patch(
            "app.services.subscription.task_completion_handler.call_executor_delete",
            new_callable=AsyncMock,
        ) as mock_delete:
            await handler._cleanup_executor_container(mock_event_without_executor)

            mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_failure_handled(self, handler, mock_event_with_executor):
        """Test that cleanup failure is handled gracefully."""
        with patch(
            "app.services.subscription.task_completion_handler.call_executor_delete",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = False

            # Should not raise exception
            await handler._cleanup_executor_container(mock_event_with_executor)

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_exception_handled(self, handler, mock_event_with_executor):
        """Test that cleanup exception is handled gracefully."""
        with patch(
            "app.services.subscription.task_completion_handler.call_executor_delete",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.side_effect = Exception("Connection error")

            # Should not raise exception
            await handler._cleanup_executor_container(mock_event_with_executor)

            mock_delete.assert_called_once()


class TestTaskCompletedEvent:
    """Tests for TaskCompletedEvent with executor fields."""

    def test_event_with_executor_fields(self):
        """Test that TaskCompletedEvent can be created with executor fields."""
        event = TaskCompletedEvent(
            task_id=1,
            subtask_id=2,
            user_id=123,
            status="COMPLETED",
            executor_name="test-executor",
            executor_namespace="default",
        )

        assert event.executor_name == "test-executor"
        assert event.executor_namespace == "default"

    def test_event_without_executor_fields(self):
        """Test that TaskCompletedEvent works without executor fields (backward compat)."""
        event = TaskCompletedEvent(
            task_id=1,
            subtask_id=2,
            user_id=123,
            status="COMPLETED",
        )

        assert event.executor_name is None
        assert event.executor_namespace is None
