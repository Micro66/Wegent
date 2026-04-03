# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for IM conversation Team selection behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.channels.callback import BaseCallbackInfo, ChannelType
from app.services.channels.commands import CommandType, ParsedCommand
from app.services.channels.device_selection import DeviceSelection
from app.services.channels.handler import BaseChannelHandler, MessageContext
from app.services.execution.router import CommunicationMode


class DummyHandler(BaseChannelHandler[dict, BaseCallbackInfo]):
    """Minimal handler for testing shared IM channel behavior."""

    def parse_message(self, raw_data):
        return MessageContext(
            content="",
            sender_id="",
            sender_name=None,
            conversation_id="",
            conversation_type="private",
            is_mention=False,
            raw_message=raw_data,
            extra_data={},
        )

    async def resolve_user(self, db, message_context):
        return None

    async def send_text_reply(self, message_context, text):
        return True

    def create_callback_info(self, message_context):
        return BaseCallbackInfo(
            channel_type=self.channel_type,
            channel_id=self.channel_id,
            conversation_id=message_context.conversation_id,
        )

    def get_callback_service(self):
        return None

    async def create_streaming_emitter(self, message_context):
        return None


@pytest.fixture
def handler():
    """Create a shared handler instance."""
    return DummyHandler(
        channel_type=ChannelType.DINGTALK,
        channel_id=1,
        get_default_team_id=lambda: 100,
        get_default_model_name=lambda: "default-model",
    )


@pytest.fixture
def user():
    """Create a minimal user object."""
    return SimpleNamespace(id=7)


@pytest.fixture
def message_context():
    """Create a minimal message context."""
    return MessageContext(
        content="/new",
        sender_id="sender-1",
        sender_name="Alice",
        conversation_id="conv-1",
        conversation_type="group",
        is_mention=True,
        raw_message={},
        extra_data={},
    )


class TestConversationTeamState:
    """Tests for conversation Team cache helpers."""

    @pytest.mark.asyncio
    async def test_set_conversation_team_id_without_ttl(self, handler):
        """Conversation Team selection should not use TTL."""
        with patch("app.services.channels.handler.cache_manager") as mock_cache:
            mock_cache.set = AsyncMock(return_value=True)

            result = await handler._set_conversation_team_id("conv-1", 7, 123)

        assert result is True
        mock_cache.set.assert_awaited_once_with(
            "channel:conv_team:dingtalk:conv-1:7",
            123,
            expire=None,
        )

    @pytest.mark.asyncio
    async def test_get_conversation_team_id(self, handler):
        """Conversation Team selection should be loaded from Redis."""
        with patch("app.services.channels.handler.cache_manager") as mock_cache:
            mock_cache.get = AsyncMock(return_value=321)

            team_id = await handler._get_conversation_team_id("conv-1", 7)

        assert team_id == 321
        mock_cache.get.assert_awaited_once_with("channel:conv_team:dingtalk:conv-1:7")


class TestNewCommandBehavior:
    """Tests for /new command semantics."""

    @pytest.mark.asyncio
    async def test_new_command_clears_task_but_not_team(
        self, handler, user, message_context
    ):
        """Starting a new conversation should keep the selected Team."""
        handler.send_text_reply = AsyncMock(return_value=True)
        handler._delete_conversation_task_id = AsyncMock()
        handler._delete_conversation_team_id = AsyncMock()

        await handler._handle_command(
            db=MagicMock(),
            user=user,
            command=ParsedCommand(command=CommandType.NEW),
            message_context=message_context,
        )

        handler._delete_conversation_task_id.assert_awaited_once_with("conv-1", 7)
        handler._delete_conversation_team_id.assert_not_called()


class TestAgentsCommandBehavior:
    """Tests for /agents command behavior."""

    @pytest.mark.asyncio
    async def test_agents_command_lists_available_teams(
        self, handler, user, message_context
    ):
        """The agents command should render current and default markers."""
        handler.send_text_reply = AsyncMock(return_value=True)
        handler._resolve_conversation_team = AsyncMock(
            return_value=(SimpleNamespace(id=200, name="Code Assistant"), False)
        )

        with patch(
            "app.services.adapters.team_kinds.team_kinds_service.get_user_teams",
            return_value=[
                {"id": 100, "name": "Default Assistant", "namespace": "default"},
                {"id": 200, "name": "Code Assistant", "namespace": "default"},
            ],
        ):
            await handler._handle_command(
                db=MagicMock(),
                user=user,
                command=ParsedCommand(command=CommandType.AGENTS),
                message_context=message_context,
            )

        sent_message = handler.send_text_reply.await_args.args[1]
        assert "Code Assistant" in sent_message
        assert "⭐ 当前" in sent_message
        assert "[默认]" in sent_message

    @pytest.mark.asyncio
    async def test_agents_command_switches_team_and_clears_task_context(
        self, handler, user, message_context
    ):
        """Switching Team should update Team selection and reset task context."""
        handler.send_text_reply = AsyncMock(return_value=True)
        handler._set_conversation_team_id = AsyncMock(return_value=True)
        handler._delete_conversation_task_id = AsyncMock()

        with patch(
            "app.services.adapters.team_kinds.team_kinds_service.get_user_teams",
            return_value=[
                {"id": 100, "name": "Default Assistant", "namespace": "default"},
                {"id": 200, "name": "Code Assistant", "namespace": "default"},
            ],
        ):
            await handler._handle_command(
                db=MagicMock(),
                user=user,
                command=ParsedCommand(command=CommandType.AGENTS, argument="2"),
                message_context=message_context,
            )

        handler._set_conversation_team_id.assert_awaited_once_with("conv-1", 7, 200)
        handler._delete_conversation_task_id.assert_awaited_once_with("conv-1", 7)

    @pytest.mark.asyncio
    async def test_agents_reset_clears_team_and_task_context(
        self, handler, user, message_context
    ):
        """Resetting Team should remove Team selection and reset task context."""
        handler.send_text_reply = AsyncMock(return_value=True)
        handler._delete_conversation_team_id = AsyncMock(return_value=True)
        handler._delete_conversation_task_id = AsyncMock()

        await handler._handle_command(
            db=MagicMock(),
            user=user,
            command=ParsedCommand(command=CommandType.AGENTS, argument="reset"),
            message_context=message_context,
        )

        handler._delete_conversation_team_id.assert_awaited_once_with("conv-1", 7)
        handler._delete_conversation_task_id.assert_awaited_once_with("conv-1", 7)


class TestStatusBehavior:
    """Tests for /status command Team display."""

    @pytest.mark.asyncio
    async def test_status_uses_conversation_team_label(
        self, handler, user, message_context
    ):
        """Status should show the effective Team for the current conversation."""
        handler.send_text_reply = AsyncMock(return_value=True)
        handler._resolve_conversation_team = AsyncMock(
            return_value=(SimpleNamespace(id=200, name="Code Assistant"), False)
        )

        with (
            patch(
                "app.services.channels.handler.device_selection_manager.get_selection",
                AsyncMock(return_value=DeviceSelection.default()),
            ),
            patch(
                "app.services.channels.handler.model_selection_manager.get_selection",
                AsyncMock(return_value=None),
            ),
        ):
            await handler._handle_status_command(
                db=MagicMock(), user=user, message_context=message_context
            )

        sent_message = handler.send_text_reply.await_args.args[1]
        assert "当前会话智能体" in sent_message
        assert "Code Assistant" in sent_message


class TestMessageFailureBehavior:
    """Tests for IM error replies when processing fails."""

    @pytest.mark.asyncio
    async def test_handle_message_replies_with_error_when_chat_processing_fails(
        self, handler
    ):
        """Chat processing failures should be returned to the IM caller."""
        handler.parse_message = MagicMock(
            return_value=MessageContext(
                content="hello",
                sender_id="sender-1",
                sender_name="Alice",
                conversation_id="conv-1",
                conversation_type="private",
                is_mention=False,
                raw_message={},
                extra_data={},
            )
        )
        handler.resolve_user = AsyncMock(return_value=SimpleNamespace(id=7))
        handler._process_chat_message = AsyncMock(
            side_effect=ValueError("Bot developer-bot has no model configured")
        )
        handler.send_text_reply = AsyncMock(return_value=True)

        result = await handler.handle_message(
            {
                "content": "hello",
                "sender_id": "sender-1",
                "conversation_id": "conv-1",
            }
        )

        assert result is False
        handler.send_text_reply.assert_awaited()
        sent_text = handler.send_text_reply.await_args.args[1]
        assert "消息发送失败" in sent_text
        assert "no model configured" in sent_text


class TestChatCallbackRegistrationBehavior:
    """Tests for chat callback registration in async execution modes."""

    @pytest.mark.asyncio
    async def test_registers_callback_info_and_active_emitter_for_http_callback_chat(
        self, handler, message_context
    ):
        """HTTP callback chats should persist callback info and reuse the live emitter."""
        callback_service = MagicMock()
        callback_service.save_callback_info = AsyncMock()
        callback_service.register_active_emitter = MagicMock()
        handler.get_callback_service = MagicMock(return_value=callback_service)
        streaming_emitter = AsyncMock()
        request = SimpleNamespace()

        with patch(
            "app.services.execution.execution_dispatcher.router.route",
            return_value=SimpleNamespace(mode=CommunicationMode.HTTP_CALLBACK),
        ):
            await handler._register_chat_callback_if_needed(
                task_id=42,
                message_context=message_context,
                request=request,
                streaming_emitter=streaming_emitter,
            )

        callback_service.save_callback_info.assert_awaited_once()
        saved_info = callback_service.save_callback_info.await_args.kwargs[
            "callback_info"
        ]
        assert saved_info.conversation_id == "conv-1"
        callback_service.register_active_emitter.assert_called_once_with(
            42, streaming_emitter
        )

    @pytest.mark.asyncio
    async def test_skips_callback_registration_for_non_http_callback_chat(
        self, handler, message_context
    ):
        """Non-callback execution modes should not register IM callback tracking."""
        callback_service = MagicMock()
        callback_service.save_callback_info = AsyncMock()
        callback_service.register_active_emitter = MagicMock()
        handler.get_callback_service = MagicMock(return_value=callback_service)

        with patch(
            "app.services.execution.execution_dispatcher.router.route",
            return_value=SimpleNamespace(mode=CommunicationMode.INPROCESS),
        ):
            await handler._register_chat_callback_if_needed(
                task_id=42,
                message_context=message_context,
                request=SimpleNamespace(),
                streaming_emitter=AsyncMock(),
            )

        callback_service.save_callback_info.assert_not_awaited()
        callback_service.register_active_emitter.assert_not_called()
