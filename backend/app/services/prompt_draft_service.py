# SPDX-FileCopyrightText: 2026 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Prompt draft generation service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.subtask import Subtask, SubtaskRole
from app.models.task import TaskResource
from app.models.user import User
from app.services import chat_shell_model_service
from app.services.prompt_draft.fallback import (
    _looks_like_meta_prompt as _prompt_draft_looks_like_meta_prompt,
)
from app.services.prompt_draft.fallback import (
    _looks_like_meta_title as _prompt_draft_looks_like_meta_title,
)
from app.services.prompt_draft.fallback import (
    build_dynamic_fallback as _build_prompt_draft_dynamic_fallback,
)
from app.services.prompt_draft.generation import (
    safe_model_config_for_logging as _safe_prompt_draft_model_config_for_logging,
)
from app.services.prompt_draft.modeling import (
    resolve_prompt_draft_model_config as _resolve_prompt_draft_model_config,
)
from app.services.prompt_draft.pipeline import (
    build_generation_messages as _build_prompt_draft_generation_messages,
)
from app.services.prompt_draft.pipeline import (
    build_prompt_generation_system_prompt as _build_prompt_draft_generation_system_prompt,
)
from app.services.prompt_draft.pipeline import (
    build_title_generation_messages as _build_prompt_draft_title_generation_messages,
)
from app.services.prompt_draft.pipeline import (
    build_title_generation_system_prompt as _build_prompt_draft_title_generation_system_prompt,
)
from app.services.prompt_draft.pipeline import (
    format_conversation_material as _format_prompt_draft_conversation_material,
)
from app.services.prompt_draft.pipeline import (
    generate_prompt_draft_stream_result as _generate_prompt_draft_stream_result,
)
from app.services.prompt_draft.pipeline import (
    generate_prompt_text as _prompt_draft_generate_prompt_text,
)
from app.services.prompt_draft.pipeline import (
    normalize_title as _normalize_prompt_draft_title,
)
from app.services.prompt_draft.pipeline import (
    run_skill_generation as _run_prompt_draft_skill_generation,
)
from app.services.prompt_draft.pipeline import (
    stream_prompt_text_generation as _stream_prompt_draft_text_generation,
)
from app.services.prompt_draft.pipeline import (
    validate_prompt_contract as _validate_prompt_draft_contract,
)
from app.services.prompt_draft.transcript import (
    collect_conversation_blocks as _collect_prompt_draft_conversation_blocks,
)
from app.services.prompt_draft.transcript import (
    extract_assistant_turn_blocks as _extract_prompt_draft_assistant_turn_blocks,
)
from app.services.task_member_service import task_member_service

logger = logging.getLogger(__name__)
TITLE_MAX_LENGTH = 18


class PromptDraftTaskNotFoundError(Exception):
    """Raised when the target task cannot be accessed by current user."""


class PromptDraftConversationTooShortError(Exception):
    """Raised when conversation content is insufficient for prompt extraction."""


def _safe_model_config_for_logging(model_config: dict[str, Any]) -> str:
    return _safe_prompt_draft_model_config_for_logging(model_config)


def _extract_text_blocks(content: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(content, str):
        normalized = content.strip()
        if normalized:
            texts.append(normalized)
        return texts
    if not isinstance(content, list):
        return texts
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str):
            normalized = text.strip()
            if normalized:
                texts.append(normalized)
    return texts


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if not isinstance(raw_arguments, str) or not raw_arguments.strip():
        return {}
    try:
        parsed = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _summarize_tool_call(tool_call: dict[str, Any]) -> str | None:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None
    name = str(function.get("name") or "").strip()
    if not name:
        return None

    arguments = _parse_tool_arguments(function.get("arguments"))
    if name == "load_skill":
        skill_name = str(arguments.get("skill_name") or "").strip()
        if skill_name:
            return f"尝试加载技能 {skill_name}"
        return "尝试加载技能"
    return f"尝试调用工具 {name}"


def _summarize_tool_result(message: dict[str, Any]) -> str | None:
    tool_name = str(message.get("name") or "").strip()
    content = str(message.get("content") or "").strip()
    if tool_name == "load_skill":
        match = re.search(r"Skill '([^']+)' has been loaded", content)
        if match:
            return f"已加载技能 {match.group(1)}"
        return "已执行技能加载"
    lowered = content.lower()
    if "error" in lowered or "failed" in lowered:
        shortened = content[:80]
        return f"工具 {tool_name or 'unknown'} 执行失败: {shortened}"
    return None


def _extract_assistant_turn_blocks(result: Any) -> list[tuple[str, str]]:
    return _extract_prompt_draft_assistant_turn_blocks(result)


def _collect_conversation_blocks(db: Session, task_id: int) -> list[tuple[str, str]]:
    return _collect_prompt_draft_conversation_blocks(db, task_id)


def _resolve_model_config(
    db: Session,
    current_user: User,
    requested_model_name: str | None,
) -> tuple[dict[str, Any] | None, str]:
    return _resolve_prompt_draft_model_config(db, current_user, requested_model_name)


def _validate_prompt_contract(prompt: str) -> None:
    _validate_prompt_draft_contract(prompt)


def _format_conversation_material(conversation_blocks: list[tuple[str, str]]) -> str:
    return _format_prompt_draft_conversation_material(conversation_blocks)


def _build_generation_messages(
    conversation_blocks: list[tuple[str, str]],
) -> list[dict[str, str]]:
    return _build_prompt_draft_generation_messages(conversation_blocks)


def _build_prompt_generation_system_prompt() -> str:
    return _build_prompt_draft_generation_system_prompt()


def _build_title_generation_messages(prompt: str) -> list[dict[str, str]]:
    return _build_prompt_draft_title_generation_messages(prompt)


def _build_title_generation_system_prompt() -> str:
    return _build_prompt_draft_title_generation_system_prompt()


def _normalize_title(title: str, *, fallback: str) -> str:
    return _normalize_prompt_draft_title(title, fallback=fallback)


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
    return _prompt_draft_looks_like_meta_prompt(prompt)


def _looks_like_meta_title(title: str) -> bool:
    return _prompt_draft_looks_like_meta_title(title)


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


def _build_prompt_retry_message(invalid_prompt: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "你刚才的输出不合格。"
            "问题在于你描述了“会话提炼/会话记录/prompt草案”这个提炼任务本身，"
            "而不是从材料里提炼未来助手应承担的真实任务领域与协作规则。"
            "禁止出现“会话提炼助手”“用户会话记录”“上述会话”“prompt草案”等字样。"
            "请重新输出最终 prompt 正文。\n\n"
            f"无效输出如下：\n{invalid_prompt}"
        ),
    }


async def _generate_prompt_text(
    *,
    model_id: str,
    input_messages: list[dict[str, str]],
    prompt_instructions: str,
    metadata: dict[str, Any],
    model_config: dict[str, Any],
) -> str:
    return await _prompt_draft_generate_prompt_text(
        model_id=model_id,
        input_messages=input_messages,
        prompt_instructions=prompt_instructions,
        metadata=metadata,
        model_config=model_config,
    )


def _build_dynamic_fallback(
    conversation_blocks: list[tuple[str, str]],
    task_title: str | None,
) -> tuple[str, str]:
    return _build_prompt_draft_dynamic_fallback(conversation_blocks, task_title)


async def _run_skill_generation(
    model_config: dict[str, Any],
    conversation_blocks: list[tuple[str, str]],
    selected_model_name: str,
    task_id: int,
    user_id: int,
    fallback_title: str,
) -> dict[str, Any]:
    return await _run_prompt_draft_skill_generation(
        model_config=model_config,
        conversation_blocks=conversation_blocks,
        selected_model_name=selected_model_name,
        task_id=task_id,
        user_id=user_id,
        fallback_title=fallback_title,
    )


async def _stream_prompt_text_generation(
    *,
    model_id: str,
    input_messages: list[dict[str, str]],
    prompt_instructions: str,
    metadata: dict[str, Any],
    model_config: dict[str, Any],
) -> AsyncIterator[str]:
    async for delta in _stream_prompt_draft_text_generation(
        model_id=model_id,
        input_messages=input_messages,
        prompt_instructions=prompt_instructions,
        metadata=metadata,
        model_config=model_config,
    ):
        yield delta


def _prepare_prompt_draft_context(
    db: Session,
    task_id: int,
    current_user: User,
    model: str | None,
) -> dict[str, Any]:
    task = (
        db.query(TaskResource)
        .filter(
            TaskResource.id == task_id,
            TaskResource.kind == "Task",
            TaskResource.is_active.in_(
                [TaskResource.STATE_ACTIVE, TaskResource.STATE_SUBSCRIPTION]
            ),
        )
        .first()
    )
    if not task or not task_member_service.is_member(db, task_id, current_user.id):
        raise PromptDraftTaskNotFoundError("task_not_found")

    blocks = _collect_conversation_blocks(db, task_id)
    if len(blocks) < 2:
        raise PromptDraftConversationTooShortError("conversation_too_short")

    fallback_title, fallback_prompt = _build_dynamic_fallback(
        conversation_blocks=blocks,
        task_title=((task.json or {}).get("spec") or {}).get("title"),
    )

    model_config, selected_model = _resolve_model_config(db, current_user, model)
    return {
        "task": task,
        "blocks": blocks,
        "fallback_title": fallback_title,
        "fallback_prompt": fallback_prompt,
        "model_config": model_config,
        "selected_model": selected_model,
    }


def validate_prompt_draft_context(
    db: Session,
    task_id: int,
    current_user: User,
    model: str | None = None,
) -> None:
    """Validate preconditions for prompt draft generation."""
    _prepare_prompt_draft_context(
        db=db, task_id=task_id, current_user=current_user, model=model
    )


async def generate_prompt_draft_stream(
    db: Session,
    task_id: int,
    current_user: User,
    model: str | None = None,
    source: str | None = None,
    current_prompt: str | None = None,
    regenerate: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Generate prompt draft as stream events without DB persistence."""

    del source

    context = _prepare_prompt_draft_context(
        db=db, task_id=task_id, current_user=current_user, model=model
    )
    model_config = context["model_config"]
    selected_model = context["selected_model"]
    fallback_title = context["fallback_title"]
    fallback_prompt = context["fallback_prompt"]
    blocks = context["blocks"]

    if not model_config:
        created_at = datetime.now(timezone.utc).isoformat()
        yield {"type": "prompt_done", "prompt": fallback_prompt}
        yield {"type": "title_done", "title": fallback_title}
        yield {
            "type": "completed",
            "data": {
                "title": fallback_title,
                "prompt": fallback_prompt,
                "model": selected_model,
                "version": 1,
                "created_at": created_at,
            },
        }
        return

    async for event in _generate_prompt_draft_stream_result(
        task_id=task_id,
        user_id=current_user.id,
        selected_model=selected_model,
        model_config=model_config,
        fallback_title=fallback_title,
        fallback_prompt=fallback_prompt,
        conversation_blocks=blocks,
        current_prompt=current_prompt,
        regenerate=regenerate,
    ):
        yield event


def generate_prompt_draft(
    db: Session,
    task_id: int,
    current_user: User,
    model: str | None = None,
    source: str | None = None,
    current_prompt: str | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    """Generate a prompt draft from task conversation."""

    del source

    context = _prepare_prompt_draft_context(
        db=db, task_id=task_id, current_user=current_user, model=model
    )
    task = context["task"]
    blocks = context["blocks"]
    fallback_title = context["fallback_title"]
    fallback_prompt = context["fallback_prompt"]
    model_config = context["model_config"]
    selected_model = context["selected_model"]
    if model_config:
        try:
            import asyncio

            return asyncio.run(
                _run_skill_generation(
                    model_config=model_config,
                    conversation_blocks=blocks,
                    selected_model_name=selected_model,
                    task_id=task.id,
                    user_id=current_user.id,
                    fallback_title=fallback_title,
                    current_prompt=current_prompt,
                    regenerate=regenerate,
                )
            )
        except Exception:
            logger.warning(
                "Prompt draft generation failed via chat_shell, using dynamic fallback: "
                "task_id=%s user_id=%s model=%s",
                task.id,
                current_user.id,
                selected_model,
                exc_info=True,
            )

    return {
        "title": fallback_title,
        "prompt": fallback_prompt,
        "model": selected_model,
        "version": 1,
        "created_at": datetime.now(timezone.utc),
    }
