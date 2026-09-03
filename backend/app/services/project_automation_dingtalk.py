# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

"""DingTalk message ingress for project automation rules."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.delivery import (
    CloudProject,
    LoopItem,
    LoopItemAttachment,
    ProjectAutomationRule,
    ProjectIncomingEvent,
)
from app.models.user import User
from app.schemas.base_role import BaseRole
from app.schemas.delivery import LoopItemCreate
from app.services.channels.dingtalk.sender import DingTalkRobotSender
from app.services.cloud_projects.access import require_cloud_project_role
from app.services.delivery.storage import delivery_storage
from app.services.loop_item_status_history import project_board_statuses
from app.services.loop_items.external_provider import external_loop_item_provider
from app.services.loop_items.provider_router import loop_item_provider_router
from app.services.project_automation_dingtalk_binding import (
    project_automation_dingtalk_binding_service,
)
from app.services.project_automation_domain import ProjectAutomationEvent, metadata
from app.services.project_automations import project_automation_processor
from shared.telemetry.decorators import trace_async

Download = Callable[[str], Awaitable[tuple[bytes, str]]]


@dataclass(frozen=True)
class DingTalkMedia:
    download_code: str
    filename: str


@dataclass(frozen=True)
class DingTalkIssueInput:
    problem: str
    supplemental: str
    original_author: str
    original_time: str
    media: tuple[DingTalkMedia, ...]


def _strings(value: object, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        current = value.get(key)
        if isinstance(current, str) and current.strip():
            found.append(current.strip())
        for child in value.values():
            found.extend(_strings(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_strings(child, key))
    return found


def _content(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _message_text(content: object) -> str:
    content = _content(content)
    if isinstance(content, str):
        return content.strip()
    texts = _strings(content, "text")
    if not texts and isinstance(content, dict):
        direct = content.get("content")
        if isinstance(direct, str) and direct.strip():
            texts.append(direct.strip())
    return "\n".join(texts).strip()


def _replied_author(callback: dict, replied: dict) -> str:
    named_author = replied.get("senderNick") or replied.get("senderName")
    if named_author:
        return str(named_author)
    sender_id = str(replied.get("senderId") or "")
    callback_sender_ids = {
        str(callback.get("senderId") or ""),
        str(callback.get("senderStaffId") or ""),
    }
    if sender_id and sender_id in callback_sender_ids:
        return str(callback.get("senderNick") or sender_id)
    return sender_id


def _display_time(value: str) -> str:
    if not value:
        return "未知"
    try:
        timestamp = float(value)
    except ValueError:
        return value
    if timestamp > 100_000_000_000:
        timestamp /= 1000
    try:
        return (
            datetime.fromtimestamp(timestamp, timezone.utc)
            .astimezone()
            .isoformat(timespec="seconds")
        )
    except (OverflowError, OSError, ValueError):
        return value


def parse_dingtalk_issue(callback: dict) -> DingTalkIssueInput:
    text = callback.get("text")
    text = text if isinstance(text, dict) else {}
    supplemental = _message_text(text.get("content"))
    replied = text.get("repliedMsg")
    if not isinstance(replied, dict):
        content = _content(callback.get("content"))
        problem = supplemental or _message_text(content)
        media = tuple(
            DingTalkMedia(code, f"dingtalk-image-{index}.png")
            for index, code in enumerate(_strings(content, "downloadCode"), 1)
        )
        return DingTalkIssueInput(
            problem=problem,
            supplemental="",
            original_author=str(callback.get("senderNick") or ""),
            original_time=str(
                callback.get("createAt") or callback.get("createdAt") or ""
            ),
            media=media,
        )
    content = _content(replied.get("content"))
    problem = _message_text(content)
    codes = _strings(content, "downloadCode")
    media = tuple(
        DingTalkMedia(code, f"dingtalk-image-{index}.png")
        for index, code in enumerate(codes, 1)
    )
    return DingTalkIssueInput(
        problem=problem,
        supplemental=supplemental,
        original_author=_replied_author(callback, replied),
        original_time=str(replied.get("createdAt") or replied.get("createAt") or ""),
        media=media,
    )


class ProjectAutomationDingTalkIngress:
    @trace_async(
        span_name="project_automation.dingtalk.ingress",
        tracer_name="backend.project_automation",
        extract_attributes=lambda self, db, **kwargs: {
            "channel.id": kwargs.get("channel_id", 0),
            "message.group": kwargs.get("is_group", False),
            "message.mentioned": kwargs.get("is_mention", False),
        },
    )
    async def handle(
        self,
        db: Session,
        *,
        channel_id: int,
        callback: dict,
        user: User | None,
        is_group: bool,
        is_mention: bool,
        download: Download,
        robot_sender: DingTalkRobotSender,
    ) -> bool:
        if not is_group or not is_mention:
            return False
        conversation_id = str(callback.get("conversationId") or "")
        msg_id = str(callback.get("msgId") or "")
        if not conversation_id or not msg_id:
            return False
        if user is not None:
            pending = await project_automation_dingtalk_binding_service.consume_pending(
                db, channel_id, user.id
            )
            if pending:
                return await self._bind(
                    db, pending, callback, conversation_id, msg_id, robot_sender
                )
        binding = project_automation_dingtalk_binding_service.find_active(
            db, channel_id, conversation_id
        )
        if binding is None:
            return False
        if user is None:
            await self._tag(callback, robot_sender, "未识别用户")
            return True
        try:
            access = require_cloud_project_role(
                db, binding.project_id, user.id, BaseRole.Developer
            )
        except HTTPException:
            await self._tag(callback, robot_sender, "无项目权限")
            return True
        rule = db.get(ProjectAutomationRule, binding.automation_id)
        if (
            rule is None
            or rule.status != "enabled"
            or metadata(rule).get("event_source") != "dingtalk"
        ):
            await self._tag(callback, robot_sender, "自动化已停用")
            return True
        parsed = parse_dingtalk_issue(callback)
        if not parsed.problem and not parsed.media:
            await self._tag(callback, robot_sender, "内容为空")
            return True
        event = self._event(db, rule, channel_id, msg_id, user.id)
        if event.status == "acknowledged":
            return True
        if event.status == "failed":
            await self._tag(callback, robot_sender, "此前处理失败")
            return True
        if event.status == "dispatched":
            await self._ack(event, callback, robot_sender, db)
            return True
        stored = (event.metadata_json or {}).get("attachments")
        staged = [dict(item) for item in stored] if isinstance(stored, list) else []
        if not staged and parsed.media:
            try:
                staged = await self._stage_media(
                    access.project, event, parsed.media, download
                )
                event.metadata_json = {
                    **dict(event.metadata_json or {}),
                    "attachments": staged,
                }
                db.commit()
            except Exception:
                event.status = "failed"
                event.metadata_json = {"reason": "media_download_failed"}
                db.commit()
                await self._tag(callback, robot_sender, "图片处理失败")
                return True
        try:
            await self._create_and_dispatch(
                db, access.project, rule, event, user, callback, parsed, staged
            )
        except Exception:
            db.rollback()
            raise
        await self._ack(event, callback, robot_sender, db)
        return True

    async def _bind(
        self,
        db: Session,
        pending: dict,
        callback: dict,
        conversation_id: str,
        msg_id: str,
        sender: DingTalkRobotSender,
    ) -> bool:
        try:
            project_automation_dingtalk_binding_service.bind(
                db,
                pending,
                conversation_id,
                str(callback.get("conversationTitle") or "钉钉群"),
            )
        except HTTPException:
            await self._tag(callback, sender, "绑定失败")
            return True
        await self._tag(callback, sender, "绑定成功")
        return True

    @staticmethod
    async def _tag(
        callback: dict,
        sender: DingTalkRobotSender,
        text: str,
    ) -> None:
        if not await sender.reply_text_emotion(
            str(callback.get("msgId") or ""),
            str(callback.get("conversationId") or ""),
            text,
        ):
            raise RuntimeError(f"DingTalk text tag was not accepted: {text}")

    @staticmethod
    def _event(
        db: Session,
        rule: ProjectAutomationRule,
        channel_id: int,
        msg_id: str,
        user_id: int,
    ) -> ProjectIncomingEvent:
        public_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"wegent:project-automation:dingtalk-message:{channel_id}:{msg_id}",
            )
        )
        event = (
            db.query(ProjectIncomingEvent)
            .filter(ProjectIncomingEvent.public_id == public_id)
            .one_or_none()
        )
        if event is not None:
            return event
        event = ProjectIncomingEvent(
            public_id=public_id,
            cloud_project_id=rule.cloud_project_id,
            parent_id=rule.id,
            source="dingtalk",
            status="processing",
            created_by_user_id=user_id,
            metadata_json={"channel_id": channel_id, "msg_id": msg_id},
        )
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(ProjectIncomingEvent)
                .filter(ProjectIncomingEvent.public_id == public_id)
                .one_or_none()
            )
            if existing is None:
                raise
            return existing
        db.refresh(event)
        return event

    @staticmethod
    async def _stage_media(
        project: CloudProject,
        event: ProjectIncomingEvent,
        media: tuple[DingTalkMedia, ...],
        download: Download,
    ) -> list[dict[str, object]]:
        staged: list[dict[str, object]] = []
        max_bytes = settings.DELIVERY_MAX_ASSET_SIZE_MB * 1024 * 1024
        try:
            for index, item in enumerate(media, 1):
                content, content_type = await download(item.download_code)
                if not content or len(content) > max_bytes:
                    raise ValueError("Invalid DingTalk media size")
                extension = mimetypes.guess_extension(content_type) or ".bin"
                filename = f"dingtalk-image-{index}{extension}"
                key = f"projects/{project.public_id}/incoming/dingtalk/{event.public_id}/{index}"
                delivery_storage.put_bytes(key, content, content_type)
                staged.append(
                    {
                        "key": key,
                        "filename": filename,
                        "content_type": content_type,
                        "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
        except Exception:
            delivery_storage.remove_objects([str(item["key"]) for item in staged])
            raise
        return staged

    async def _create_and_dispatch(
        self,
        db: Session,
        project: CloudProject,
        rule: ProjectAutomationRule,
        event: ProjectIncomingEvent,
        user: User,
        callback: dict,
        parsed: DingTalkIssueInput,
        staged: list[dict[str, object]],
    ) -> None:
        item_id = str(event.loop_item_id or "")
        if not item_id and project.task_provider in {"github", "gitlab"}:
            marker = f"<!-- wegent-dingtalk:{event.public_id} -->"
            existing = next(
                (
                    candidate
                    for candidate in external_loop_item_provider.list(
                        db, project.id, user.id
                    )
                    if marker in str(candidate.get("description") or "")
                ),
                None,
            )
            if existing is not None:
                item_id = str(existing["id"])
                event.loop_item_id = item_id
                event.status = "issue_created"
                event.metadata_json = {
                    **dict(event.metadata_json or {}),
                    "attachments": staged,
                }
                db.commit()
        if not item_id:
            description = self._description(callback, parsed, event.public_id)
            title = next(
                (line.strip() for line in parsed.problem.splitlines() if line.strip()),
                f"钉钉图片反馈 - {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}",
            )[:255]
            statuses = project_board_statuses(project)
            routed = loop_item_provider_router.create(
                db,
                project,
                user,
                LoopItemCreate(
                    title=title,
                    description=description,
                    status=statuses[0][0] if statuses else "todo",
                ),
                automation_context={
                    "source": "dingtalk",
                    "automation_rule_id": str(rule.id),
                    "incoming_event_id": str(event.id),
                },
                assign_creator_if_unassigned=False,
                commit=False,
            )
            item_id = str(routed.values["id"])
            event.loop_item_id = item_id
            event.status = "issue_created"
            event.metadata_json = {
                **dict(event.metadata_json or {}),
                "attachments": staged,
            }
            db.commit()
        item = db.get(LoopItem, item_id)
        if item is None:
            item = external_loop_item_provider.ensure_shadow(db, item_id, user.id)
        self._register_attachments(db, project, item, user.id, staged)
        dispatched = await project_automation_processor.process(
            db,
            ProjectAutomationEvent(
                event_type="task.created",
                project_id=str(project.id),
                subject_id=item_id,
                source="dingtalk",
                actor_user_id=user.id,
                payload={
                    "title": item.title,
                    "description": item.description,
                    "status": item.status,
                    "priority": item.priority,
                    "tags": item.tags,
                    "incoming_event_id": str(event.id),
                },
            ),
            automation_id=str(rule.id),
        )
        if dispatched != 1:
            raise RuntimeError("DingTalk automation was not dispatched exactly once")
        event.status = "dispatched"
        db.commit()

    @staticmethod
    def _register_attachments(
        db: Session,
        project: CloudProject,
        item: LoopItem,
        user_id: int,
        staged: list[dict[str, object]],
    ) -> None:
        existing = {
            row.sha256
            for row in db.query(LoopItemAttachment)
            .filter(LoopItemAttachment.loop_item_id == item.id)
            .all()
        }
        for stored in staged:
            digest = str(stored["sha256"])
            if digest in existing:
                continue
            attachment_id = str(uuid.uuid4())
            target = f"projects/{project.public_id}/loop-items/{item.id}/attachments/{attachment_id}"
            delivery_storage.copy_object(str(stored["key"]), target)
            db.add(
                LoopItemAttachment(
                    id=attachment_id,
                    loop_item_id=item.id,
                    display_name=str(stored["filename"]),
                    object_key=target,
                    content_type=str(stored["content_type"]),
                    size_bytes=int(stored["size"]),
                    sha256=digest,
                    created_by_user_id=user_id,
                )
            )
        db.commit()

    @staticmethod
    def _description(
        callback: dict, parsed: DingTalkIssueInput, event_public_id: str
    ) -> str:
        group = str(callback.get("conversationTitle") or "钉钉群")
        submitter = str(callback.get("senderNick") or "未知")
        submitted_at = (
            datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        )
        return (
            f"## 原问题\n\n{parsed.problem or '（图片反馈）'}\n\n"
            f"## 补充说明\n\n{parsed.supplemental or '无'}\n\n"
            "## 钉钉来源\n\n"
            f"- 群：{group}\n- 原作者：{parsed.original_author or submitter}\n"
            f"- 原消息时间：{_display_time(parsed.original_time)}\n"
            f"- 提交人：{submitter}\n- 提交时间：{submitted_at}\n\n"
            f"<!-- wegent-dingtalk:{event_public_id} -->"
        )

    @staticmethod
    async def _ack(
        event: ProjectIncomingEvent,
        callback: dict,
        sender: DingTalkRobotSender,
        db: Session,
    ) -> None:
        await ProjectAutomationDingTalkIngress._tag(callback, sender, "收到")
        event.status = "acknowledged"
        db.commit()


project_automation_dingtalk_ingress = ProjectAutomationDingTalkIngress()
