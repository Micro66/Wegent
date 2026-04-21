# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Helpers for reading GroupChat configuration from task JSON.

This module is shared between backend and chat_shell to avoid circular imports.
"""

from typing import Any

DEFAULT_GROUP_CHAT_HISTORY_WINDOW = {
    "maxDays": 2,
    "maxMessages": 200,
}


def get_group_chat_team_refs(task_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return GroupChat team refs from new or legacy task schema."""
    spec = (task_json or {}).get("spec", {})

    team_refs = spec.get("teamRefs")
    if team_refs:
        return [team_ref for team_ref in team_refs if isinstance(team_ref, dict)]

    legacy_team_ref = spec.get("teamRef")
    if isinstance(legacy_team_ref, dict):
        return [legacy_team_ref]

    return []


def is_allowed_group_chat_team(
    task_json: dict[str, Any] | None, team_id: int | None
) -> bool:
    """Return whether the provided team ID is present in configured team refs."""
    if team_id is None:
        return False

    for team_ref in get_group_chat_team_refs(task_json):
        ref_id = team_ref.get("id", team_ref.get("team_id"))
        if ref_id == team_id:
            return True

    return False


def get_group_chat_history_window(task_json: dict[str, Any] | None) -> dict[str, int]:
    """Return configured GroupChat history window with defaults applied."""
    spec = (task_json or {}).get("spec", {})
    history_window = (
        spec.get("groupChatConfig", {}).get("historyWindow", {})
        if isinstance(spec.get("groupChatConfig"), dict)
        else {}
    )

    return {
        "maxDays": int(
            history_window.get("maxDays", DEFAULT_GROUP_CHAT_HISTORY_WINDOW["maxDays"])
        ),
        "maxMessages": int(
            history_window.get(
                "maxMessages", DEFAULT_GROUP_CHAT_HISTORY_WINDOW["maxMessages"]
            )
        ),
    }
