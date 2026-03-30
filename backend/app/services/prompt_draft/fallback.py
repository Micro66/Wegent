# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from app.services.prompt_draft.prompt_contract import build_markdown_prompt

TITLE_MAX_LENGTH = 18
PROMPT_META_PHRASES = (
    "会话提炼助手",
    "用户会话记录",
    "给定的用户会话记录",
    "上述会话",
    "prompt草案",
    "提炼可复用",
)
TITLE_META_PHRASES = (
    "会话提炼",
    "会话记录",
    "prompt草案",
    "生成提示词",
    "提示词生成",
)


def _is_low_signal_text(text: str) -> bool:
    normalized = "".join(ch for ch in text.strip() if not ch.isspace())
    if not normalized:
        return True
    if len(normalized) <= 2:
        return True
    if normalized.isdigit():
        return True
    return False


def _infer_assistant_identity(user_lines: list[str]) -> tuple[str, str]:
    joined = " ".join(user_lines)
    if any(keyword in joined for keyword in ("流程图", "mermaid", "架构图", "时序图")):
        return (
            "流程图协作助手",
            "帮助用户梳理流程、补齐关键信息，并输出可执行的流程图方案",
        )
    if any(keyword in joined for keyword in ("代码", "重构", "调试", "测试")):
        return "研发协作助手", "帮助用户澄清研发需求，并输出可执行的研发方案"
    if any(keyword in joined for keyword in ("产品", "需求", "PRD", "原型")):
        return "产品协作助手", "帮助用户梳理产品需求，并输出清晰的产品分析与交付方案"
    return "协作助手", "根据用户需求输出清晰、可执行的结果"


def _normalize_match_text(text: str) -> str:
    return "".join(ch.lower() for ch in text if not ch.isspace())


def _looks_like_meta_prompt(prompt: str) -> bool:
    normalized = _normalize_match_text(prompt)
    return any(
        _normalize_match_text(phrase) in normalized for phrase in PROMPT_META_PHRASES
    )


def _looks_like_meta_title(title: str) -> bool:
    normalized = _normalize_match_text(title)
    if any(
        _normalize_match_text(phrase) in normalized for phrase in TITLE_META_PHRASES
    ):
        return True
    for prefix_length in range(4, min(9, len(normalized)) + 1):
        prefix = normalized[:prefix_length]
        if prefix and normalized.count(prefix) >= 2:
            return True
    return False


def _extract_style_preferences(user_lines: list[str]) -> list[str]:
    preferences: list[str] = []
    keywords = ("先", "不要", "必须", "优先", "保持", "简洁", "结构", "步骤", "结论")
    for text in user_lines:
        normalized = " ".join(text.split())
        if _is_low_signal_text(normalized):
            continue
        if not any(keyword in normalized for keyword in keywords):
            continue
        if normalized in preferences:
            continue
        preferences.append(normalized)
        if len(preferences) >= 2:
            break
    return preferences


def _build_domain_defaults(
    assistant_identity: str,
) -> tuple[str, list[str], list[str], list[str], str]:
    if assistant_identity == "流程图协作助手":
        return (
            "流程图协作提示词",
            [
                "先识别流程目标、参与对象和关键步骤。",
                "信息不足时先追问缺失节点、分支和判断条件。",
            ],
            [
                "优先沉淀可复用的流程图协作方式，而不是复述一次性背景。",
                "输出内容应围绕流程图任务本身，避免偏离到无关领域。",
            ],
            [
                "结果应结构清晰，便于继续细化为流程图或 Mermaid 描述。",
            ],
            "帮助用户梳理流程、补齐关键信息，并输出可执行的流程图方案",
        )
    if assistant_identity == "研发协作助手":
        return (
            "研发协作提示词",
            [
                "先明确目标、约束和验收标准，再展开实现步骤。",
                "信息不足时优先补齐风险点、边界条件和验证方式。",
            ],
            [
                "优先输出可执行方案，避免空泛描述。",
                "在冲突要求之间，优先选择更稳定、可验证的约束。",
            ],
            [
                "结果应便于直接进入实现、调试或评审环节。",
            ],
            "帮助用户澄清研发需求，并输出可执行的研发方案",
        )
    if assistant_identity == "产品协作助手":
        return (
            "产品协作提示词",
            [
                "先澄清目标用户、使用场景和交付物边界。",
                "信息不足时优先补齐关键流程、约束和成功标准。",
            ],
            [
                "优先沉淀能复用到后续需求分析与交付中的协作规则。",
                "避免把一次性会议语气或临时背景写成长期约束。",
            ],
            [
                "结果应便于继续产出方案、文档或原型。",
            ],
            "帮助用户梳理产品需求，并输出清晰的产品分析与交付方案",
        )
    return (
        "协作提示词",
        [
            "先明确目标、缺失信息和交付预期，再展开具体内容。",
            "信息不足时优先追问关键约束，避免直接猜测。",
        ],
        [
            "优先保留稳定、可执行的协作规则，忽略一次性客套和闲聊。",
            "输出应贴近用户真实任务，不引入会话外的新领域或流程。",
        ],
        [
            "结果应简洁、清晰，并可直接复用。",
        ],
        "根据用户需求输出清晰、可执行的结果",
    )


def build_dynamic_fallback(
    conversation_blocks: list[tuple[str, str]],
    task_title: str | None,
) -> tuple[str, str]:
    user_lines = [
        content.strip()
        for block_type, content in conversation_blocks
        if block_type == "user" and content.strip()
    ]

    assistant_identity, responsibility = _infer_assistant_identity(user_lines)
    title, work_modes, principles, output_requirements, responsibility = (
        _build_domain_defaults(assistant_identity)
    )
    stable_preferences = _extract_style_preferences(user_lines)

    normalized_task_title = (task_title or "").strip()
    if normalized_task_title and not _looks_like_meta_title(normalized_task_title):
        lowered = normalized_task_title.lower()
        if "prompt draft" not in lowered and "task" not in lowered:
            title = normalized_task_title[:TITLE_MAX_LENGTH]

    prompt = build_markdown_prompt(
        intro=f"你是{assistant_identity}，负责{responsibility}。",
        work_modes=[*work_modes, *stable_preferences],
        principles=principles,
        output_requirements=output_requirements,
    )
    return title, prompt


__all__ = [
    "build_dynamic_fallback",
    "_looks_like_meta_prompt",
    "_looks_like_meta_title",
]
