# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

import pytest


@pytest.mark.unit
class TestGroupChatConfig:
    def test_reads_team_refs_from_new_group_chat_schema(self):
        """New group chat tasks should expose all configured team refs."""
        from app.services.chat.group_chat_config import (
            get_group_chat_team_refs,
            is_allowed_group_chat_team,
        )

        task_json = {
            "spec": {
                "is_group_chat": True,
                "teamRefs": [
                    {"name": "agent-a", "namespace": "default", "id": 11},
                    {"name": "agent-b", "namespace": "default", "id": 22},
                ],
            }
        }

        assert get_group_chat_team_refs(task_json) == [
            {"name": "agent-a", "namespace": "default", "id": 11},
            {"name": "agent-b", "namespace": "default", "id": 22},
        ]
        assert is_allowed_group_chat_team(task_json, 11) is True
        assert is_allowed_group_chat_team(task_json, 99) is False

    def test_falls_back_to_legacy_single_team_ref(self):
        """Legacy group chat tasks should still expose their single team ref."""
        from app.services.chat.group_chat_config import (
            get_group_chat_team_refs,
            is_allowed_group_chat_team,
        )

        task_json = {
            "spec": {
                "is_group_chat": True,
                "teamRef": {"name": "legacy-agent", "namespace": "default", "id": 7},
            }
        }

        assert get_group_chat_team_refs(task_json) == [
            {"name": "legacy-agent", "namespace": "default", "id": 7}
        ]
        assert is_allowed_group_chat_team(task_json, 7) is True

    def test_uses_default_history_window_when_missing(self):
        """Group chat history window should default to 2 days and 200 messages."""
        from app.services.chat.group_chat_config import get_group_chat_history_window

        task_json = {
            "spec": {
                "is_group_chat": True,
                "teamRef": {"name": "legacy-agent", "namespace": "default"},
            }
        }

        assert get_group_chat_history_window(task_json) == {
            "maxDays": 2,
            "maxMessages": 200,
        }
