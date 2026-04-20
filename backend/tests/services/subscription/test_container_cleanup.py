# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for subscription task container cleanup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.events import TaskCompletedEvent
from app.models.task import TaskResource
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


@pytest.fixture
def mock_subscription_task():
    """Create a mock TaskResource for subscription task."""
    task = MagicMock(spec=TaskResource)
    task.is_active = TaskResource.STATE_SUBSCRIPTION
    task.json = {"metadata": {"labels": {"type": "subscription"}}}
    return task


@pytest.fixture
def mock_regular_task():
    """Create a mock TaskResource for regular task."""
    task = MagicMock(spec=TaskResource)
    task.is_active = TaskResource.STATE_ACTIVE
    task.json = {"metadata": {"labels": {}}}
    return task


class TestCleanupExecutorContainer:
    """Tests for _cleanup_executor_container method."""

    @pytest.mark.asyncio
    async def test_cleanup_with_executor_name(
        self, handler, mock_event_with_executor, mock_subscription_task
    ):
        """Test container cleanup when executor_name is provided for subscription task."""
        mock_db = MagicMock()
        # First query returns TaskResource, second query returns Subtask
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_subscription_task,
            MagicMock(),  # subtask mock
        ]

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = {"status": "success"}

            await handler._cleanup_executor_container(mock_db, mock_event_with_executor)

            mock_delete.assert_called_once_with(
                executor_name="test-executor-abc123",
                executor_namespace="default",
            )

    @pytest.mark.asyncio
    async def test_cleanup_without_executor_name(
        self, handler, mock_event_without_executor
    ):
        """Test that cleanup is skipped when executor_name is None."""
        mock_db = MagicMock()

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            await handler._cleanup_executor_container(
                mock_db, mock_event_without_executor
            )

            mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_skipped_for_regular_task(
        self, handler, mock_event_with_executor, mock_regular_task
    ):
        """Test that cleanup is skipped for non-subscription tasks."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_regular_task
        )

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            await handler._cleanup_executor_container(mock_db, mock_event_with_executor)

            mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_skipped_when_task_not_found(
        self, handler, mock_event_with_executor
    ):
        """Test that cleanup is skipped when task is not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            await handler._cleanup_executor_container(mock_db, mock_event_with_executor)

            mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_failure_handled(
        self, handler, mock_event_with_executor, mock_subscription_task
    ):
        """Test that cleanup failure is handled gracefully."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_subscription_task
        )

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.return_value = {
                "status": "error",
                "error": "Container not found",
            }

            # Should not raise exception
            await handler._cleanup_executor_container(mock_db, mock_event_with_executor)

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_exception_handled(
        self, handler, mock_event_with_executor, mock_subscription_task
    ):
        """Test that cleanup exception is handled gracefully."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_subscription_task
        )

        with patch(
            "app.services.subscription.task_completion_handler.executor_kinds_service.delete_executor_task_async",
            new_callable=AsyncMock,
        ) as mock_delete:
            mock_delete.side_effect = Exception("Connection error")

            # Should not raise exception
            await handler._cleanup_executor_container(mock_db, mock_event_with_executor)

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
