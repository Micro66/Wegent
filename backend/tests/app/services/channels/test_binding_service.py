# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for IM Channel Binding Service."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.user import User
from app.schemas.im_channel import (
    IMChannelUserBinding,
    IMGroupBinding,
    UpdateIMBindingRequest,
)
from app.services.channels.binding_service import (
    BINDING_PENDING_INDEX_PREFIX,
    BINDING_PENDING_PREFIX,
    BINDING_SESSION_TTL,
    IMChannelBindingService,
    binding_service,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def sample_user():
    """Create a sample user with empty preferences."""
    user = MagicMock(spec=User)
    user.id = 1
    user.preferences = json.dumps({})
    return user


@pytest.fixture
def sample_user_with_bindings():
    """Create a sample user with existing IM channel bindings."""
    user = MagicMock(spec=User)
    user.id = 1
    user.preferences = json.dumps(
        {
            "im_channels": {
                "1": {
                    "channel_type": "dingtalk",
                    "private_team_id": 100,
                    "group_bindings": [
                        {
                            "conversation_id": "cid_abc123",
                            "group_name": "Test Group",
                            "team_id": 200,
                            "bound_at": "2026-04-16T10:00:00+00:00",
                        }
                    ],
                }
            }
        }
    )
    return user


@pytest.fixture
def sample_channel():
    """Create a sample Messager channel."""
    channel = MagicMock(spec=Kind)
    channel.id = 1
    channel.name = "Test DingTalk Channel"
    channel.kind = "Messager"
    channel.json = json.dumps({"channelType": "dingtalk"})
    return channel


class TestGetUserBindings:
    """Tests for get_user_bindings method."""

    def test_get_user_bindings_empty_preferences(self, mock_db, sample_user):
        """Test getting bindings for user with empty preferences."""
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user

        result = IMChannelBindingService.get_user_bindings(mock_db, 1)

        assert result == []

    def test_get_user_bindings_no_user(self, mock_db):
        """Test getting bindings for non-existent user."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = IMChannelBindingService.get_user_bindings(mock_db, 999)

        assert result == []

    def test_get_user_bindings_with_data(
        self, mock_db, sample_user_with_bindings, sample_channel
    ):
        """Test getting bindings with existing data."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        # Mock the channel query
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        result = IMChannelBindingService.get_user_bindings(mock_db, 1)

        assert len(result) == 1
        binding = result[0]
        assert binding.channel_id == 1
        assert binding.channel_name == "Test DingTalk Channel"
        assert binding.channel_type == "dingtalk"
        assert binding.private_team_id == 100
        assert len(binding.group_bindings) == 1
        assert binding.group_bindings[0].conversation_id == "cid_abc123"
        assert binding.group_bindings[0].team_id == 200

    def test_get_user_bindings_dict_preferences(
        self, mock_db, sample_user_with_bindings, sample_channel
    ):
        """Test getting bindings when preferences is already a dict."""
        sample_user_with_bindings.preferences = {
            "im_channels": {
                "1": {
                    "channel_type": "dingtalk",
                    "private_team_id": 100,
                    "group_bindings": [],
                }
            }
        }
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        result = IMChannelBindingService.get_user_bindings(mock_db, 1)

        assert len(result) == 1
        assert result[0].channel_id == 1


class TestUpdateBinding:
    """Tests for update_binding method."""

    def test_update_private_team_id(self, mock_db, sample_user, sample_channel):
        """Test updating private_team_id."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_user,  # First call for user
            sample_channel,  # Second call for channel
            sample_user,  # For get_user_bindings after update
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        request = UpdateIMBindingRequest(private_team_id=123)
        result = IMChannelBindingService.update_binding(mock_db, 1, 1, request)

        assert result is not None
        assert result.private_team_id == 123
        mock_db.commit.assert_called_once()

    def test_update_add_group_binding(self, mock_db, sample_user, sample_channel):
        """Test adding a new group binding."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_user,
            sample_channel,
            sample_user,  # For get_user_bindings after update
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        group = IMGroupBinding(
            conversation_id="cid_new",
            group_name="New Group",
            team_id=300,
        )
        request = UpdateIMBindingRequest(group=group)

        result = IMChannelBindingService.update_binding(mock_db, 1, 1, request)

        assert result is not None
        assert len(result.group_bindings) == 1
        assert result.group_bindings[0].conversation_id == "cid_new"

    def test_update_existing_group_binding(
        self, mock_db, sample_user_with_bindings, sample_channel
    ):
        """Test updating an existing group binding preserves bound_at."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_user_with_bindings,
            sample_user_with_bindings,  # For get_user_bindings after update
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        # Update existing group binding
        group = IMGroupBinding(
            conversation_id="cid_abc123",  # Same as existing
            group_name="Updated Group Name",
            team_id=250,
        )
        request = UpdateIMBindingRequest(group=group)

        result = IMChannelBindingService.update_binding(mock_db, 1, 1, request)

        assert result is not None
        assert len(result.group_bindings) == 1
        assert result.group_bindings[0].group_name == "Updated Group Name"
        assert result.group_bindings[0].team_id == 250

    def test_update_binding_user_not_found(self, mock_db):
        """Test updating binding for non-existent user."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        request = UpdateIMBindingRequest(private_team_id=123)
        result = IMChannelBindingService.update_binding(mock_db, 999, 1, request)

        assert result is None

    def test_update_binding_channel_not_found(self, mock_db, sample_user):
        """Test updating binding for non-existent channel."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_user,
            None,  # Channel not found
        ]

        request = UpdateIMBindingRequest(private_team_id=123)
        result = IMChannelBindingService.update_binding(mock_db, 1, 999, request)

        assert result is None


class TestRemoveGroupBinding:
    """Tests for remove_group_binding method."""

    def test_remove_existing_group_binding(
        self, mock_db, sample_user_with_bindings, sample_channel
    ):
        """Test removing an existing group binding."""
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_user_with_bindings,
            sample_user_with_bindings,  # For get_user_bindings after update
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = [
            sample_channel
        ]

        result = IMChannelBindingService.remove_group_binding(
            mock_db, 1, 1, "cid_abc123"
        )

        assert result is not None
        assert len(result.group_bindings) == 0
        mock_db.commit.assert_called_once()

    def test_remove_nonexistent_group_binding(self, mock_db, sample_user_with_bindings):
        """Test removing a non-existent group binding."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        result = IMChannelBindingService.remove_group_binding(
            mock_db, 1, 1, "cid_nonexistent"
        )

        assert result is None

    def test_remove_group_binding_user_not_found(self, mock_db):
        """Test removing group binding for non-existent user."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = IMChannelBindingService.remove_group_binding(
            mock_db, 999, 1, "cid_abc123"
        )

        assert result is None


class TestResolveTeamForMessage:
    """Tests for resolve_team_for_message method."""

    def test_resolve_group_chat_with_binding(self, mock_db, sample_user_with_bindings):
        """Test resolving team for group chat with existing binding."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        # Create message context mock
        message_context = MagicMock()
        message_context.conversation_type = "group"
        message_context.conversation_id = "cid_abc123"

        result = IMChannelBindingService.resolve_team_for_message(
            mock_db, 1, 1, message_context
        )

        assert result == 200  # team_id from group binding

    def test_resolve_group_chat_no_binding_fallback(
        self, mock_db, sample_user_with_bindings
    ):
        """Test resolving team for group chat without binding falls back to private_team_id."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        message_context = MagicMock()
        message_context.conversation_type = "group"
        message_context.conversation_id = "cid_unknown"

        result = IMChannelBindingService.resolve_team_for_message(
            mock_db, 1, 1, message_context
        )

        assert result == 100  # private_team_id

    def test_resolve_private_chat(self, mock_db, sample_user_with_bindings):
        """Test resolving team for private chat."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        message_context = MagicMock()
        message_context.conversation_type = "private"
        message_context.conversation_id = "cid_private"

        result = IMChannelBindingService.resolve_team_for_message(
            mock_db, 1, 1, message_context
        )

        assert result == 100  # private_team_id

    def test_resolve_with_dict_context(self, mock_db, sample_user_with_bindings):
        """Test resolving team with dict-style message context."""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            sample_user_with_bindings
        )

        message_context = {
            "conversation_type": "group",
            "conversation_id": "cid_abc123",
        }

        result = IMChannelBindingService.resolve_team_for_message(
            mock_db, 1, 1, message_context
        )

        assert result == 200

    def test_resolve_no_bindings(self, mock_db, sample_user):
        """Test resolving team when user has no bindings."""
        mock_db.query.return_value.filter.return_value.first.return_value = sample_user

        message_context = MagicMock()
        message_context.conversation_type = "private"
        message_context.conversation_id = "cid_private"

        result = IMChannelBindingService.resolve_team_for_message(
            mock_db, 1, 1, message_context
        )

        assert result is None


class TestRedisSessionMethods:
    """Tests for Redis session management methods."""

    @pytest.mark.asyncio
    async def test_start_binding_session(self):
        """Test starting a binding session."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.set = AsyncMock(return_value=True)

            result = await IMChannelBindingService.start_binding_session(1, 1)

            assert result is True
            # Should set both session key and index
            assert mock_cache.set.call_count == 2

            # Check session key format
            calls = mock_cache.set.call_args_list
            session_key = calls[0][0][0]
            assert session_key.startswith(BINDING_PENDING_PREFIX)
            assert "1:1" in session_key

    @pytest.mark.asyncio
    async def test_start_binding_session_failure(self):
        """Test starting a binding session when cache fails."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.set = AsyncMock(return_value=False)

            result = await IMChannelBindingService.start_binding_session(1, 1)

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_binding_session(self):
        """Test cancelling a binding session."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.delete = AsyncMock(return_value=True)

            result = await IMChannelBindingService.cancel_binding_session(1, 1)

            assert result is True
            # Should delete both session key and index
            assert mock_cache.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_get_binding_session(self):
        """Test getting an active binding session."""
        session_data = {
            "user_id": 1,
            "channel_id": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.get = AsyncMock(return_value=session_data)

            result = await IMChannelBindingService.get_binding_session(1, 1)

            assert result == session_data

    @pytest.mark.asyncio
    async def test_get_binding_session_not_found(self):
        """Test getting a non-existent binding session."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)

            result = await IMChannelBindingService.get_binding_session(1, 1)

            assert result is None


class TestHandleBindingFromMessage:
    """Tests for handle_binding_from_message method."""

    @pytest.mark.asyncio
    async def test_handle_binding_from_message_success(
        self, mock_db, sample_user, sample_channel
    ):
        """Test successful binding from message."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.get = AsyncMock(
                return_value={
                    "user_id": 1,
                    "channel_id": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            mock_cache.delete = AsyncMock(return_value=True)
            mock_cache.set = AsyncMock(return_value=True)

            mock_db.query.return_value.filter.return_value.first.side_effect = [
                sample_user,
                sample_channel,
                sample_user,  # For get_user_bindings after update
            ]
            mock_db.query.return_value.filter.return_value.all.return_value = [
                sample_channel
            ]

            result = await IMChannelBindingService.handle_binding_from_message(
                db=mock_db,
                user_id=1,
                channel_id=1,
                conversation_id="cid_from_msg",
                group_name="Group From Message",
                team_id=500,
            )

            assert result is not None
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_binding_from_message_no_session(self, mock_db):
        """Test binding from message without active session."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)

            result = await IMChannelBindingService.handle_binding_from_message(
                db=mock_db,
                user_id=1,
                channel_id=1,
                conversation_id="cid_from_msg",
                group_name="Group From Message",
                team_id=500,
            )

            assert result is None


class TestSingleton:
    """Tests for the singleton instance."""

    def test_singleton_instance_exists(self):
        """Test that singleton instance exists."""
        assert binding_service is not None
        assert isinstance(binding_service, IMChannelBindingService)
