# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for PreviewSubscriptionTool.

This module tests:
- Preview generation without creating subscription
- Preview storage with TTL (Redis-based)
- Preview retrieval and cleanup
- Preview table formatting
- Input validation
- Expiration configuration
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from chat_shell.services.storage.preview_storage import (
    clear_preview,
    delete_preview,
    get_preview,
    store_preview,
)
from chat_shell.tools.builtin.preview_subscription import (
    PreviewSubscriptionInput,
    PreviewSubscriptionTool,
    get_preview_data,
)


class TestPreviewSubscriptionInput:
    """Tests for PreviewSubscriptionInput schema."""

    def test_cron_trigger_input_valid(self):
        """Test valid cron trigger input."""
        # Arrange & Act
        input_data = PreviewSubscriptionInput(
            display_name="Daily Report",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Generate daily report for {{date}}",
        )

        # Assert
        assert input_data.display_name == "Daily Report"
        assert input_data.trigger_type == "cron"
        assert input_data.cron_expression == "0 9 * * *"
        assert "{{date}}" in input_data.prompt_template

    def test_interval_trigger_input_valid(self):
        """Test valid interval trigger input."""
        # Arrange & Act
        input_data = PreviewSubscriptionInput(
            display_name="Hourly Check",
            trigger_type="interval",
            interval_value=2,
            interval_unit="hours",
            prompt_template="Check system status",
        )

        # Assert
        assert input_data.trigger_type == "interval"
        assert input_data.interval_value == 2
        assert input_data.interval_unit == "hours"

    def test_one_time_trigger_input_valid(self):
        """Test valid one-time trigger input."""
        # Arrange & Act
        input_data = PreviewSubscriptionInput(
            display_name="One-time Task",
            trigger_type="one_time",
            execute_at="2025-01-20T09:00:00",
            prompt_template="Execute scheduled task",
        )

        # Assert
        assert input_data.trigger_type == "one_time"
        assert input_data.execute_at == "2025-01-20T09:00:00"

    def test_preserve_history_default_false(self):
        """Test that preserve_history defaults to False."""
        # Arrange & Act
        input_data = PreviewSubscriptionInput(
            display_name="Test",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Test",
        )

        # Assert
        assert input_data.preserve_history is False
        assert input_data.history_message_count == 10

    def test_default_configuration_values(self):
        """Test default configuration values."""
        # Arrange & Act
        input_data = PreviewSubscriptionInput(
            display_name="Test",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Test",
        )

        # Assert
        assert input_data.retry_count == 1
        assert input_data.timeout_seconds == 600
        assert input_data.description is None

    def test_expiration_fixed_date_input_valid(self):
        """Test valid fixed date expiration input."""
        input_data = PreviewSubscriptionInput(
            display_name="Test",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Test",
            expiration_type="fixed_date",
            expiration_fixed_date="2025-12-31T23:59:59",
        )
        assert input_data.expiration_type == "fixed_date"
        assert input_data.expiration_fixed_date == "2025-12-31T23:59:59"

    def test_expiration_duration_days_input_valid(self):
        """Test valid duration days expiration input."""
        input_data = PreviewSubscriptionInput(
            display_name="Test",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Test",
            expiration_type="duration_days",
            expiration_duration_days=7,
        )
        assert input_data.expiration_type == "duration_days"
        assert input_data.expiration_duration_days == 7

    def test_expiration_no_config(self):
        """Test that expiration is optional."""
        input_data = PreviewSubscriptionInput(
            display_name="Test",
            trigger_type="cron",
            cron_expression="0 9 * * *",
            prompt_template="Test",
        )
        assert input_data.expiration_type is None
        assert input_data.expiration_fixed_date is None
        assert input_data.expiration_duration_days is None


class TestPreviewStorage:
    """Tests for Redis-based preview storage mechanism."""

    def test_store_preview(self):
        """Test storing preview data in Redis."""
        # Arrange
        preview_id = "preview_test_store"
        data = {"display_name": "Test", "trigger_type": "cron"}

        # Act
        result = store_preview(preview_id, data)

        # Assert
        assert result is True
        # Verify by retrieving
        stored = get_preview(preview_id)
        assert stored == data
        # Cleanup
        delete_preview(preview_id)

    def test_get_preview_existing(self):
        """Test retrieving existing preview from Redis."""
        # Arrange
        preview_id = "preview_test_get"
        data = {"display_name": "Test", "trigger_type": "cron"}
        store_preview(preview_id, data)

        # Act
        result = get_preview(preview_id)

        # Assert
        assert result == data
        # Cleanup
        delete_preview(preview_id)

    def test_get_preview_nonexistent(self):
        """Test retrieving non-existent preview."""
        # Act
        result = get_preview("preview_nonexistent_xyz")

        # Assert
        assert result is None

    def test_delete_preview(self):
        """Test deleting specific preview from Redis."""
        # Arrange
        preview_id = "preview_test_delete"
        store_preview(preview_id, {"test": "data"})

        # Act
        result = delete_preview(preview_id)

        # Assert
        assert result is True
        assert get_preview(preview_id) is None

    def test_clear_preview_public_interface(self):
        """Test clear_preview public interface function."""
        # Arrange
        preview_id = "preview_test_clear"
        store_preview(preview_id, {"test": "data"})

        # Act
        clear_preview(preview_id)

        # Assert
        assert get_preview(preview_id) is None

    def test_get_preview_data_public_interface(self):
        """Test get_preview_data public interface function."""
        # Arrange
        preview_id = "preview_test_public"
        data = {"display_name": "Test Task"}
        store_preview(preview_id, data)

        # Act
        result = get_preview_data(preview_id)

        # Assert
        assert result == data
        # Cleanup
        delete_preview(preview_id)


class TestPreviewSubscriptionToolValidation:
    """Tests for PreviewSubscriptionTool input validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test-team",
            team_namespace="default",
            timezone="Asia/Shanghai",
        )

    def test_validate_cron_missing_expression(self):
        """Test validation fails when cron expression is missing."""
        # Act
        error = self.tool._validate_trigger_config(
            trigger_type="cron",
            cron_expression=None,
            interval_value=None,
            interval_unit=None,
            execute_at=None,
        )

        # Assert
        assert error is not None
        assert "cron_expression is required" in error

    def test_validate_cron_invalid_expression(self):
        """Test validation fails for invalid cron expression."""
        # Act
        error = self.tool._validate_trigger_config(
            trigger_type="cron",
            cron_expression="0 9 * *",  # Only 4 parts instead of 5
            interval_value=None,
            interval_unit=None,
            execute_at=None,
        )

        # Assert
        assert error is not None
        assert "Invalid cron expression" in error

    def test_validate_interval_missing_value(self):
        """Test validation fails when interval value is missing."""
        # Act
        error = self.tool._validate_trigger_config(
            trigger_type="interval",
            cron_expression=None,
            interval_value=None,
            interval_unit="hours",
            execute_at=None,
        )

        # Assert
        assert error is not None
        assert "interval_value is required" in error

    def test_validate_one_time_missing_execute_at(self):
        """Test validation fails when execute_at is missing."""
        # Act
        error = self.tool._validate_trigger_config(
            trigger_type="one_time",
            cron_expression=None,
            interval_value=None,
            interval_unit=None,
            execute_at=None,
        )

        # Assert
        assert error is not None
        assert "execute_at is required" in error

    @pytest.mark.asyncio
    async def test_validate_expiration_fixed_date_missing_date(self):
        """Test validation fails when fixed_date is missing."""
        # Act
        result = await self.tool._arun(
            display_name="Test",
            trigger_type="cron",
            prompt_template="Test",
            cron_expression="0 9 * * *",
            expiration_type="fixed_date",
        )

        # Assert
        response = json.loads(result)
        assert response["success"] is False
        assert "expiration_fixed_date is required" in response["error"]

    @pytest.mark.asyncio
    async def test_validate_expiration_duration_days_missing_days(self):
        """Test validation fails when duration_days is missing."""
        # Act
        result = await self.tool._arun(
            display_name="Test",
            trigger_type="cron",
            prompt_template="Test",
            cron_expression="0 9 * * *",
            expiration_type="duration_days",
        )

        # Assert
        response = json.loads(result)
        assert response["success"] is False
        assert "expiration_duration_days is required" in response["error"]

    @pytest.mark.asyncio
    async def test_validate_expiration_invalid_date_format(self):
        """Test validation fails for invalid date format."""
        # Act
        result = await self.tool._arun(
            display_name="Test",
            trigger_type="cron",
            prompt_template="Test",
            cron_expression="0 9 * * *",
            expiration_type="fixed_date",
            expiration_fixed_date="invalid-date",
        )

        # Assert
        response = json.loads(result)
        assert response["success"] is False
        assert "Invalid expiration_fixed_date format" in response["error"]


class TestPreviewSubscriptionToolFormatting:
    """Tests for PreviewSubscriptionTool formatting."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test-team",
            team_namespace="default",
            timezone="Asia/Shanghai",
        )

    def test_format_cron_trigger_description(self):
        """Test formatting cron trigger description."""
        # Act
        desc = self.tool._format_trigger_description(
            "cron", {"expression": "0 9 * * *", "timezone": "Asia/Shanghai"}
        )

        # Assert
        assert "0 9 * * *" in desc
        assert "Asia/Shanghai" in desc

    def test_format_interval_trigger_description(self):
        """Test formatting interval trigger description."""
        # Act
        desc = self.tool._format_trigger_description(
            "interval", {"value": 2, "unit": "hours"}
        )

        # Assert
        assert "2" in desc
        assert "小时" in desc

    def test_format_one_time_trigger_description(self):
        """Test formatting one-time trigger description."""
        # Act
        desc = self.tool._format_trigger_description(
            "one_time", {"execute_at": "2025-01-20T09:00:00", "timezone": "UTC"}
        )

        # Assert
        assert "2025-01-20T09:00:00" in desc
        assert "UTC" in desc

    def test_format_preview_table_cron(self):
        """Test formatting preview table for cron trigger."""
        # Act
        table = self.tool._format_preview_table(
            display_name="每日报告",
            description="每天早上9点生成报告",
            trigger_type="cron",
            trigger_config={"expression": "0 9 * * *", "timezone": "Asia/Shanghai"},
            prompt_template="Generate daily report",
            preserve_history=True,
            history_message_count=20,
            retry_count=2,
            timeout_seconds=1200,
            expires_at="2025-12-31T23:59:59",
        )

        # Assert
        assert "订阅任务预览" in table
        assert "每日报告" in table
        assert "0 9 * * *" in table
        assert "保留历史" in table
        assert "是" in table
        assert "过期时间" in table
        assert "2025-12-31" in table
        assert "执行" in table  # Confirmation prompt
        assert "取消" in table  # Cancel option

    def test_format_preview_table_interval(self):
        """Test formatting preview table for interval trigger."""
        # Act
        table = self.tool._format_preview_table(
            display_name="定时检查",
            description=None,
            trigger_type="interval",
            trigger_config={"value": 30, "unit": "minutes"},
            prompt_template="Check status",
            preserve_history=False,
            history_message_count=10,
            retry_count=1,
            timeout_seconds=600,
            expires_at=None,
        )

        # Assert
        assert "定时检查" in table
        assert "30" in table
        assert "分钟" in table
        assert "否" in table  # Not preserving history
        assert "过期时间" in table
        assert "无" in table  # No expiration

    def test_format_preview_table_escapes_pipe(self):
        """Test that pipe characters are escaped in markdown table."""
        # Act
        table = self.tool._format_preview_table(
            display_name="Test",
            description="Test | with pipes",
            trigger_type="cron",
            trigger_config={"expression": "0 9 * * *"},
            prompt_template="Test | prompt",
            preserve_history=False,
            history_message_count=10,
            retry_count=1,
            timeout_seconds=600,
            expires_at=None,
        )

        # Assert
        assert "\\|" in table  # Pipes should be escaped

    def test_format_preview_table_truncates_long_prompt(self):
        """Test that long prompts are truncated."""
        # Arrange
        long_prompt = "A" * 150

        # Act
        table = self.tool._format_preview_table(
            display_name="Test",
            description=None,
            trigger_type="cron",
            trigger_config={"expression": "0 9 * * *"},
            prompt_template=long_prompt,
            preserve_history=False,
            history_message_count=10,
            retry_count=1,
            timeout_seconds=600,
            expires_at=None,
        )

        # Assert - verify truncation is applied
        assert "..." in table
        # The prompt in table should be truncated (max 100 chars + "...")
        assert "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA..." in table


class TestPreviewSubscriptionToolAsyncExecution:
    """Tests for PreviewSubscriptionTool async execution."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test-team",
            team_namespace="default",
            timezone="Asia/Shanghai",
        )

    def test_sync_run_raises_not_implemented(self):
        """Test that sync _run raises NotImplementedError."""
        # Assert
        with pytest.raises(NotImplementedError):
            self.tool._run(
                display_name="Test",
                trigger_type="cron",
                prompt_template="Test",
                cron_expression="0 9 * * *",
            )

    @pytest.mark.asyncio
    async def test_arun_returns_error_for_invalid_cron(self):
        """Test that _arun returns error for invalid cron expression."""
        # Act
        result = await self.tool._arun(
            display_name="Test",
            trigger_type="cron",
            prompt_template="Test",
            cron_expression="invalid",
        )

        # Assert
        response = json.loads(result)
        assert response["success"] is False
        assert "Invalid cron expression" in response["error"]

    @pytest.mark.asyncio
    async def test_arun_generates_preview_for_valid_cron(self):
        """Test that _arun generates preview for valid cron expression."""
        # Act
        result = await self.tool._arun(
            display_name="Daily Report",
            trigger_type="cron",
            prompt_template="Generate report",
            cron_expression="0 9 * * *",
        )

        # Assert
        response = json.loads(result)
        assert response["success"] is True
        assert "preview_id" in response
        assert response["preview_id"].startswith("preview_")
        assert "execution_id" in response
        assert response["execution_id"].startswith("exec_")
        assert "preview_table" in response
        assert "订阅任务预览" in response["preview_table"]
        assert "Daily Report" in response["preview_table"]

        # Cleanup
        delete_preview(response["preview_id"])

    @pytest.mark.asyncio
    async def test_arun_stores_preview_data(self):
        """Test that _arun stores preview data in Redis."""
        # Act
        result = await self.tool._arun(
            display_name="Test Task",
            trigger_type="interval",
            prompt_template="Test prompt",
            interval_value=2,
            interval_unit="hours",
            preserve_history=True,
            history_message_count=20,
        )

        # Assert
        response = json.loads(result)
        preview_id = response["preview_id"]

        # Verify data is stored in Redis
        stored_data = get_preview(preview_id)
        assert stored_data is not None
        assert stored_data["display_name"] == "Test Task"
        assert stored_data["trigger_type"] == "interval"
        assert stored_data["preserve_history"] is True
        assert stored_data["history_message_count"] == 20
        assert stored_data["prompt_template"] == "Test prompt"
        assert stored_data["user_id"] == 1
        assert stored_data["team_id"] == 10
        assert "execution_id" in stored_data

        # Cleanup
        delete_preview(preview_id)

    @pytest.mark.asyncio
    async def test_arun_returns_execution_id(self):
        """Test that _arun returns execution_id."""
        result = await self.tool._arun(
            display_name="Test Task",
            trigger_type="cron",
            prompt_template="Test prompt",
            cron_expression="0 9 * * *",
        )

        response = json.loads(result)
        assert response["success"] is True
        assert "execution_id" in response
        assert response["execution_id"].startswith("exec_")

        # Cleanup
        delete_preview(response["preview_id"])

    @pytest.mark.asyncio
    async def test_arun_stores_expires_at_for_fixed_date(self):
        """Test that fixed_date expiration is stored as expires_at."""
        result = await self.tool._arun(
            display_name="Test Task",
            trigger_type="cron",
            prompt_template="Test prompt",
            cron_expression="0 9 * * *",
            expiration_type="fixed_date",
            expiration_fixed_date="2025-12-31T23:59:59",
        )

        response = json.loads(result)
        preview_id = response["preview_id"]

        # Verify expires_at is stored (using Redis)
        stored_data = get_preview(preview_id)
        assert stored_data is not None
        assert stored_data["expires_at"] == "2025-12-31T23:59:59"

        # Cleanup
        delete_preview(preview_id)

    @pytest.mark.asyncio
    async def test_arun_calculates_expires_at_for_duration_days(self):
        """Test that duration_days is converted to expires_at."""
        result = await self.tool._arun(
            display_name="Test Task",
            trigger_type="cron",
            prompt_template="Test prompt",
            cron_expression="0 9 * * *",
            expiration_type="duration_days",
            expiration_duration_days=7,
        )

        response = json.loads(result)
        preview_id = response["preview_id"]

        # Verify expires_at is calculated and stored (using Redis)
        stored_data = get_preview(preview_id)
        assert stored_data is not None
        assert stored_data["expires_at"] is not None

        # Verify it's a valid ISO datetime
        expires_at = datetime.fromisoformat(stored_data["expires_at"])
        # Should be approximately 7 days from now
        expected_min = datetime.now() + timedelta(days=6, hours=23)
        expected_max = datetime.now() + timedelta(days=7, hours=1)
        assert expected_min <= expires_at <= expected_max

        # Cleanup
        delete_preview(preview_id)


class TestPreviewSubscriptionToolMetadata:
    """Tests for PreviewSubscriptionTool metadata."""

    def test_tool_name(self):
        """Test tool name is correct."""
        # Arrange
        tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test",
            team_namespace="default",
            timezone="UTC",
        )

        # Assert
        assert tool.name == "preview_subscription"

    def test_tool_display_name(self):
        """Test tool display name is correct."""
        # Arrange
        tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test",
            team_namespace="default",
            timezone="UTC",
        )

        # Assert
        assert tool.display_name == "预览订阅任务"

    def test_tool_args_schema(self):
        """Test tool args schema is correct."""
        # Arrange
        tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test",
            team_namespace="default",
            timezone="UTC",
        )

        # Assert
        assert tool.args_schema == PreviewSubscriptionInput

    def test_tool_description_contains_workflow(self):
        """Test tool description contains workflow instructions."""
        # Arrange
        tool = PreviewSubscriptionTool(
            user_id=1,
            team_id=10,
            team_name="test",
            team_namespace="default",
            timezone="UTC",
        )

        # Assert
        assert "preview_subscription" in tool.description
        assert "Workflow" in tool.description
        assert "preview_subscription" in tool.description
