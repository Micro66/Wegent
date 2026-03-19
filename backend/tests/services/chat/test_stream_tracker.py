# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import patch

from app.services.chat.stream_tracker import StreamTracker


def test_get_stale_threshold_seconds_uses_configured_value():
    tracker = StreamTracker("redis://localhost:6379/0")

    with patch(
        "app.services.chat.stream_tracker.settings.STREAM_STALE_THRESHOLD_SECONDS", 45
    ):
        assert tracker._get_stale_threshold_seconds() == 45
