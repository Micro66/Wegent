# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the DingTalk channel provider."""

from types import SimpleNamespace

from app.services.channels.dingtalk.service import DingTalkChannelProvider


def test_status_reports_configuration_without_exposing_client_id() -> None:
    client_id = "client-id-that-must-not-be-exposed"
    provider = DingTalkChannelProvider(
        SimpleNamespace(
            id=145,
            name="dingtalk",
            channel_type="dingtalk",
            is_enabled=True,
            config={
                "client_id": client_id,
                "client_secret": "secret",
                "use_ai_card": False,
            },
            default_team_id=0,
            default_model_name="",
        )
    )

    status = provider.get_status()

    assert status["extra_info"]["configured"] is True
    assert client_id not in str(status)
