# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Helpers for reading GroupChat configuration from task JSON.

Re-export from shared module to maintain backward compatibility.
"""

# Re-export all functions from shared module
from shared.utils.group_chat_config import (
    DEFAULT_GROUP_CHAT_HISTORY_WINDOW,
    get_group_chat_history_window,
    get_group_chat_team_refs,
    is_allowed_group_chat_team,
)

__all__ = [
    "DEFAULT_GROUP_CHAT_HISTORY_WINDOW",
    "get_group_chat_team_refs",
    "is_allowed_group_chat_team",
    "get_group_chat_history_window",
]
