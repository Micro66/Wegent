# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for BaseChannelHandler."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.user import User
from app.services.channels import ChannelType
from app.services.channels.handler import BaseChannelHandler, MessageContext


class MockChannelHandler(BaseChannelHandler):
    """Mock implementation of BaseChannelHandler for testing."""

    def parse_message(self, raw_data):
        return raw_data

    async def resolve_user(self, db, message_context):
        return None

    async def send_text_reply(self, message_context, text):
        return True

    def create_callback_info(self, message_context):
        return None

    def get_callback_service(self):
        return None

    async def create_streaming_emitter(self, message_context):
        return None


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def sample_team():
    """Create a sample team Kind."""
    team = MagicMock(spec=Kind)
    team.id = 100
    team.kind = "Team"
    team.name = "Test Team"
    team.is_active = True
    return team


@pytest.fixture
def sample_bound_team():
    """Create a sample bound team Kind."""
    team = MagicMock(spec=Kind)
    team.id = 200
    team.kind = "Team"
    team.name = "Bound Team"
    team.is_active = True
    return team


@pytest.fixture
def message_context_private():
    """Create a sample private message context."""
    return MessageContext(
        content="Hello",
        sender_id="user123",
        sender_name="Test User",
        conversation_id="conv_private",
        conversation_type="private",
        is_mention=False,
        raw_message={},
        extra_data={},
    )


@pytest.fixture
def message_context_group():
    """Create a sample group message context."""
    return MessageContext(
        content="Hello group",
        sender_id="user123",
        sender_name="Test User",
        conversation_id="conv_group",
        conversation_type="group",
        is_mention=True,
        raw_message={},
        extra_data={},
    )


class TestResolveTeamForMessage:
    """Tests for _resolve_team_for_message method."""

    def test_resolve_from_binding_success(
        self, mock_db, sample_bound_team, message_context_private
    ):
        """Test successful team resolution from user binding."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.return_value = 200
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_bound_team
            )

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result == sample_bound_team
            mock_binding_service.resolve_team_for_message.assert_called_once_with(
                mock_db, 1, 1, message_context_private
            )

    def test_resolve_fallback_to_default_when_no_binding(
        self, mock_db, sample_team, message_context_private
    ):
        """Test fallback to default team when no binding found."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            # No binding found
            mock_binding_service.resolve_team_for_message.return_value = None
            # Default team query
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_team
            )

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result == sample_team

    def test_resolve_fallback_to_default_on_exception(
        self, mock_db, sample_team, message_context_private
    ):
        """Test fallback to default team when binding service raises exception."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            # Binding service raises exception
            mock_binding_service.resolve_team_for_message.side_effect = Exception(
                "Database error"
            )
            # Default team query
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_team
            )

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result == sample_team

    def test_resolve_team_not_found_from_binding(
        self, mock_db, sample_team, message_context_private
    ):
        """Test fallback to default when bound team not found in database."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            # Binding returns team_id but team not found
            mock_binding_service.resolve_team_for_message.return_value = 999
            # First query (for bound team) returns None
            # Second query (for default team) returns sample_team
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                None,  # Bound team not found
                sample_team,  # Default team found
            ]

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result == sample_team

    def test_resolve_inactive_team_fallback(
        self, mock_db, sample_team, message_context_private
    ):
        """Test fallback to default when bound team is inactive."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        inactive_team = MagicMock(spec=Kind)
        inactive_team.id = 200
        inactive_team.is_active = False

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.return_value = 200
            # First query returns inactive team, second returns default
            mock_db.query.return_value.filter.return_value.first.side_effect = [
                None,  # Bound team query with is_active=True returns None
                sample_team,  # Default team found
            ]

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result == sample_team

    def test_resolve_group_chat_with_binding(
        self, mock_db, sample_bound_team, message_context_group
    ):
        """Test team resolution for group chat with group binding."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.return_value = 200
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_bound_team
            )

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_group
            )

            assert result == sample_bound_team
            # Verify the binding service was called with group context
            mock_binding_service.resolve_team_for_message.assert_called_once_with(
                mock_db, 1, 1, message_context_group
            )

    def test_resolve_no_default_team_configured(self, mock_db, message_context_private):
        """Test when no default team is configured."""
        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: None,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.return_value = None

            result = handler._resolve_team_for_message(
                mock_db, 1, message_context_private
            )

            assert result is None

    def test_resolve_logs_info_when_using_binding(
        self, mock_db, sample_bound_team, message_context_private, caplog
    ):
        """Test that info log is generated when using binding."""
        import logging

        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.return_value = 200
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_bound_team
            )

            with caplog.at_level(logging.INFO):
                handler._resolve_team_for_message(mock_db, 1, message_context_private)

            assert "Resolved team from binding" in caplog.text
            assert "team_id=200" in caplog.text

    def test_resolve_logs_warning_on_exception(
        self, mock_db, sample_team, message_context_private, caplog
    ):
        """Test that warning log is generated on binding exception."""
        import logging

        handler = MockChannelHandler(
            channel_type=ChannelType.DINGTALK,
            channel_id=1,
            get_default_team_id=lambda: 100,
        )

        with patch(
            "app.services.channels.handler.binding_service"
        ) as mock_binding_service:
            mock_binding_service.resolve_team_for_message.side_effect = Exception(
                "Connection timeout"
            )
            mock_db.query.return_value.filter.return_value.first.return_value = (
                sample_team
            )

            with caplog.at_level(logging.WARNING):
                handler._resolve_team_for_message(mock_db, 1, message_context_private)

            assert "Failed to resolve user binding" in caplog.text
            assert "Connection timeout" in caplog.text
