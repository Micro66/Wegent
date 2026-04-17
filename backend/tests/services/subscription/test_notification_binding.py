# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for subscription notification binding workflow."""

from __future__ import annotations

import json
from fnmatch import fnmatch

from app.models.kind import Kind
from app.schemas.subscription import NotificationLevel
from app.services.subscription.notification_service import (
    subscription_notification_service,
)


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._store[key] = value
        return True

    def get(self, key: str):
        return self._store.get(key)

    def delete(self, key: str) -> int:
        existed = key in self._store
        self._store.pop(key, None)
        return 1 if existed else 0

    def scan_iter(self, pattern: str):
        for key in list(self._store.keys()):
            if fnmatch(key, pattern):
                yield key

    def close(self):
        return None


def _create_subscription_kind(
    test_db, owner_user_id: int, subscription_id: int = 9001
) -> Kind:
    subscription = Kind(
        id=subscription_id,
        kind="Subscription",
        user_id=owner_user_id,
        name=f"sub-{subscription_id}",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Subscription",
            "metadata": {"name": f"sub-{subscription_id}", "namespace": "default"},
            "spec": {"displayName": "Sub", "taskType": "collection"},
            "_internal": {},
        },
        is_active=True,
    )
    test_db.add(subscription)
    test_db.commit()
    test_db.refresh(subscription)
    return subscription


def test_start_and_cancel_binding_session(test_db, test_user, mocker):
    fake_redis = _FakeRedis()
    mocker.patch(
        "app.services.subscription.notification_service.redis.from_url",
        return_value=fake_redis,
    )

    _create_subscription_kind(test_db, owner_user_id=test_user.id, subscription_id=1001)

    started = subscription_notification_service.start_developer_binding_session(
        test_db,
        subscription_id=1001,
        user_id=test_user.id,
        channel_id=123,
        bind_private=True,
        bind_group=True,
    )
    assert started["status"] == "waiting"
    assert started["bind_private"] is True
    assert started["bind_group"] is True

    # New Redis key format without subscription_id
    pending_key = f"subscription:binding:pending:{test_user.id}:123"
    assert fake_redis.get(pending_key) is not None

    cancelled = subscription_notification_service.cancel_developer_binding_session(
        test_db,
        subscription_id=1001,
        user_id=test_user.id,
        channel_id=123,
    )
    assert cancelled["status"] == "cancelled"
    assert fake_redis.get(pending_key) is None


def test_group_message_emits_group_info_event(test_db, test_user, mocker):
    """Test that group binding emits WebSocket event instead of auto-updating subscription."""
    fake_redis = _FakeRedis()
    mocker.patch(
        "app.services.subscription.notification_service.redis.from_url",
        return_value=fake_redis,
    )
    emit_binding_mock = mocker.patch(
        "app.services.subscription.notification_service.emit_subscription_binding_update"
    )
    emit_group_info_mock = mocker.patch(
        "app.services.subscription.notification_service.emit_subscription_group_info"
    )

    # Create subscription without pre-existing binding config
    _create_subscription_kind(test_db, owner_user_id=test_user.id, subscription_id=1002)

    subscription_notification_service.start_developer_binding_session(
        test_db,
        subscription_id=1002,
        user_id=test_user.id,
        channel_id=123,
        bind_private=False,
        bind_group=True,
    )

    result = subscription_notification_service.handle_dingtalk_binding_from_message(
        test_db,
        user_id=test_user.id,
        channel_id=123,
        conversation_type="group",
        conversation_id="new-group-id",
        sender_id="ding-user-1",
        sender_staff_id="staff-1",
        group_name="Test Group",
    )

    assert result["matched"] is True
    assert result["completed"] is True
    assert result["group_bound"] is True
    assert result["private_bound"] is False

    # WebSocket events should be emitted
    emit_binding_mock.assert_called_once()
    emit_group_info_mock.assert_called_once_with(
        user_id=test_user.id,
        channel_id=123,
        group_name="Test Group",
        group_conversation_id="new-group-id",
    )


def test_group_message_can_also_complete_private_binding(test_db, test_user, mocker):
    fake_redis = _FakeRedis()
    mocker.patch(
        "app.services.subscription.notification_service.redis.from_url",
        return_value=fake_redis,
    )
    mocker.patch(
        "app.services.subscription.notification_service.emit_subscription_binding_update"
    )

    _create_subscription_kind(test_db, owner_user_id=test_user.id, subscription_id=1003)

    subscription_notification_service.start_developer_binding_session(
        test_db,
        subscription_id=1003,
        user_id=test_user.id,
        channel_id=123,
        bind_private=True,
        bind_group=False,
    )

    subscription_notification_service.handle_dingtalk_binding_from_message(
        test_db,
        user_id=test_user.id,
        channel_id=123,
        conversation_type="group",
        conversation_id="group-xyz",
        sender_id="ding-user-2",
        sender_staff_id="staff-2",
    )

    user_bindings = subscription_notification_service.get_user_im_bindings(
        test_db, user_id=test_user.id
    )
    channel_binding = user_bindings.get("123")
    assert channel_binding is not None
    assert channel_binding.sender_id == "ding-user-2"
    assert channel_binding.sender_staff_id == "staff-2"


def test_update_developer_settings_preserves_group_name(test_db, test_user):
    subscription = _create_subscription_kind(
        test_db, owner_user_id=test_user.id, subscription_id=1004
    )

    updated = subscription_notification_service.update_developer_settings(
        test_db,
        subscription_id=subscription.id,
        user_id=test_user.id,
        notification_level=NotificationLevel.NOTIFY,
        notification_channel_ids=[123],
        channel_binding_configs=[
            {
                "channel_id": 123,
                "bind_private": True,
                "bind_group": True,
                "group_conversation_id": "conversation-123",
                "group_name": "测试机器人",
            }
        ],
    )

    assert [item.model_dump() for item in updated.channel_binding_configs] == [
        {
            "channel_id": 123,
            "bind_private": True,
            "bind_group": True,
            "group_conversation_id": "conversation-123",
            "group_name": "测试机器人",
        }
    ]

    persisted = (
        test_db.query(Kind)
        .filter(Kind.id == subscription.id, Kind.kind == "Subscription")
        .first()
    )
    assert persisted is not None
    binding = persisted.json["_internal"]["notification_channel_bindings"]["123"]
    assert binding["group_name"] == "测试机器人"

    reloaded = subscription_notification_service.get_developer_settings(
        test_db, subscription_id=subscription.id, user_id=test_user.id
    )
    assert [item.model_dump() for item in reloaded.channel_binding_configs] == [
        {
            "channel_id": 123,
            "bind_private": True,
            "bind_group": True,
            "group_conversation_id": "conversation-123",
            "group_name": "测试机器人",
        }
    ]


def _create_messager_kind(test_db, kind_id: int = 1001) -> Kind:
    """Create a test Messager channel."""
    messager = Kind(
        id=kind_id,
        kind="Messager",
        user_id=0,  # System-level
        name=f"Test Messager {kind_id}",
        namespace="default",
        json={
            "channelType": "dingtalk",
            "isEnabled": True,
            "config": {"client_id": "test"},
        },
        is_active=True,
    )
    test_db.add(messager)
    test_db.commit()
    test_db.refresh(messager)
    return messager


def test_update_user_im_binding_preserves_agent_bindings(
    test_db,
    test_user,
):
    """Test that update_user_im_binding preserves private_team_id and group_bindings.

    This is a regression test for a bug where sending a message would
    cause agent bindings to be lost because update_user_im_binding
    was overwriting the entire im_channels entry instead of merging.
    """
    import json

    # Create a messager channel for testing
    messager_channel = _create_messager_kind(test_db)

    # Set up user with existing agent bindings
    test_user.preferences = json.dumps(
        {
            "im_channels": {
                str(messager_channel.id): {
                    "channel_type": "dingtalk",
                    "private_team_id": 123,  # User has bound a private team
                    "group_bindings": [  # User has bound some groups
                        {
                            "conversation_id": "cid_group1",
                            "group_name": "Test Group",
                            "team_id": 456,
                            "bound_at": "2026-04-16T10:00:00+00:00",
                        }
                    ],
                    "other_custom_data": "should_be_preserved",
                }
            }
        }
    )
    test_db.commit()

    # Call update_user_im_binding (this happens when user sends a message)
    subscription_notification_service.update_user_im_binding(
        db=test_db,
        user_id=test_user.id,
        channel_id=messager_channel.id,
        channel_type="dingtalk",
        sender_id="sender123",
        sender_staff_id="staff456",
        conversation_id="conv789",
    )

    # Refresh user from DB
    test_db.refresh(test_user)

    # Verify preferences
    prefs = json.loads(test_user.preferences or "{}")
    im_channels = prefs.get("im_channels", {})
    channel_data = im_channels.get(str(messager_channel.id), {})

    # Agent bindings should be preserved
    assert (
        channel_data.get("private_team_id") == 123
    ), f"private_team_id should be preserved, got {channel_data.get('private_team_id')}"

    assert (
        len(channel_data.get("group_bindings", [])) == 1
    ), f"group_bindings should be preserved, got {channel_data.get('group_bindings')}"
    assert (
        channel_data["group_bindings"][0]["conversation_id"] == "cid_group1"
    ), "group binding data should be intact"

    # New data should be added
    assert channel_data.get("sender_id") == "sender123"
    assert channel_data.get("sender_staff_id") == "staff456"
    assert channel_data.get("last_conversation_id") == "conv789"
    assert "last_active_at" in channel_data

    # Other custom data should also be preserved
    assert channel_data.get("other_custom_data") == "should_be_preserved"

    print("✓ Agent bindings preserved after message update")
