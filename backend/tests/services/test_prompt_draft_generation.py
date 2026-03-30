# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from app.services.prompt_draft.fallback import build_dynamic_fallback
from app.services.prompt_draft.generation import safe_model_config_for_logging


def test_safe_model_config_for_logging_masks_secrets():
    rendered = safe_model_config_for_logging(
        {
            "model_id": "gpt-test",
            "api_key": "sk-secret",
            "default_headers": {"Authorization": "Bearer secret-token"},
        }
    )

    assert "sk-secret" not in rendered
    assert "secret-token" not in rendered
    assert '"model_id": "gpt-test"' in rendered


def test_build_dynamic_fallback_uses_flowchart_identity_for_mermaid_requests():
    title, prompt = build_dynamic_fallback(
        conversation_blocks=[
            ("user", "帮我创建一个 mermaid 流程图"),
            ("assistant", "请告诉我主要步骤"),
        ],
        task_title="",
    )

    assert title == "流程图协作提示词"
    assert "你是流程图协作助手" in prompt
    assert "\n\n## 输出要求\n" in prompt
