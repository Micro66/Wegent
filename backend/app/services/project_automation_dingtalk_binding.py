# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Pair DingTalk groups with one project automation rule."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import cache_manager
from app.models.delivery import (
    ProjectAutomationDingTalkBinding,
)
from app.models.kind import Kind
from app.schemas.base_role import BaseRole
from app.services.cloud_projects.access import require_cloud_project_role
from app.services.project_automation_domain import integer, metadata, utcnow

PAIR_TTL_SECONDS = 600
_RULE_KEY = "project_automation:dingtalk:pair:automation:{}"
_ACTOR_KEY = "project_automation:dingtalk:pair:actor:{}:{}"


def _binding_id(automation_id: str) -> str:
    return hashlib.sha256(
        f"project-automation-dingtalk-binding:{automation_id}".encode()
    ).hexdigest()


def _group_public_id(channel_id: int, conversation_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"wegent:project-automation:dingtalk:{channel_id}:{conversation_id}",
        )
    )


def require_dingtalk_channel(db: Session, channel_id: int) -> Kind:
    channel = db.get(Kind, channel_id)
    spec = channel.json.get("spec", {}) if channel else {}
    if (
        channel is None
        or channel.kind != "Messager"
        or channel.user_id != 0
        or not channel.is_active
        or spec.get("channelType") != "dingtalk"
        or not spec.get("isEnabled", True)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DingTalk robot not found")
    return channel


class ProjectAutomationDingTalkBindingService:
    async def begin(
        self,
        db: Session,
        project_id: str,
        automation_id: str,
        user_id: int,
        version: int,
    ) -> dict:
        from app.services.project_automations import project_automation_service

        require_cloud_project_role(db, project_id, user_id, BaseRole.Maintainer)
        rule = project_automation_service._rule(db, project_id, automation_id)
        if rule.version != version:
            raise HTTPException(status.HTTP_409_CONFLICT, "Automation version conflict")
        rule_metadata = metadata(rule)
        channel_id = integer(rule_metadata.get("dingtalk_channel_id"))
        if rule_metadata.get("event_source") != "dingtalk" or channel_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Automation is not configured with a DingTalk robot",
            )
        require_dingtalk_channel(db, channel_id)
        actor_key = _ACTOR_KEY.format(user_id, channel_id)
        previous = await cache_manager.get(actor_key)
        if previous and str(previous) != automation_id:
            await cache_manager.delete(_RULE_KEY.format(previous))
        now = utcnow()
        pending = {
            "automation_id": automation_id,
            "project_id": project_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "started_at": now.isoformat(),
        }
        if not await cache_manager.set(
            _RULE_KEY.format(automation_id), pending, expire=PAIR_TTL_SECONDS
        ) or not await cache_manager.set(
            actor_key, automation_id, expire=PAIR_TTL_SECONDS
        ):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Binding service is temporarily unavailable",
            )
        return self.view(db, project_id, automation_id, user_id)

    def view(
        self, db: Session, project_id: str, automation_id: str, user_id: int
    ) -> dict:
        from app.services.project_automations import project_automation_service

        require_cloud_project_role(db, project_id, user_id, BaseRole.Reporter)
        project_automation_service._rule(db, project_id, automation_id)
        pending = cache_manager.get_sync(_RULE_KEY.format(automation_id))
        binding = self._binding(db, automation_id)
        if isinstance(pending, dict):
            started_at = str(pending.get("started_at") or "")
            from datetime import datetime

            try:
                expires_at = datetime.fromisoformat(started_at) + timedelta(
                    seconds=PAIR_TTL_SECONDS
                )
            except ValueError:
                expires_at = None
            return {
                "status": "pairing",
                "conversation_title": (
                    binding.conversation_title or None if binding else None
                ),
                "bound_at": binding.updated_at if binding else None,
                "expires_at": expires_at,
            }
        if binding:
            return {
                "status": "bound",
                "conversation_title": binding.conversation_title or None,
                "bound_at": binding.updated_at,
                "expires_at": None,
            }
        return {
            "status": "unbound",
            "conversation_title": None,
            "bound_at": None,
            "expires_at": None,
        }

    async def cancel(
        self, db: Session, project_id: str, automation_id: str, user_id: int
    ) -> dict:
        from app.services.project_automations import project_automation_service

        require_cloud_project_role(db, project_id, user_id, BaseRole.Maintainer)
        project_automation_service._rule(db, project_id, automation_id)
        pending = await cache_manager.pop(_RULE_KEY.format(automation_id))
        if isinstance(pending, dict):
            await cache_manager.delete(
                _ACTOR_KEY.format(pending.get("user_id"), pending.get("channel_id"))
            )
        return self.view(db, project_id, automation_id, user_id)

    async def unbind(
        self, db: Session, project_id: str, automation_id: str, user_id: int
    ) -> dict:
        await self.cancel(db, project_id, automation_id, user_id)
        db.query(ProjectAutomationDingTalkBinding).filter(
            ProjectAutomationDingTalkBinding.parent_id == automation_id
        ).delete(synchronize_session=False)
        db.commit()
        return self.view(db, project_id, automation_id, user_id)

    async def consume_pending(
        self, db: Session, channel_id: int, user_id: int
    ) -> dict | None:
        actor_key = _ACTOR_KEY.format(user_id, channel_id)
        automation_id = await cache_manager.pop(actor_key)
        if not automation_id:
            return None
        pending = await cache_manager.pop(_RULE_KEY.format(automation_id))
        return pending if isinstance(pending, dict) else None

    def bind(
        self,
        db: Session,
        pending: dict,
        conversation_id: str,
        conversation_title: str,
    ) -> ProjectAutomationDingTalkBinding:
        automation_id = str(pending["automation_id"])
        channel_id = int(pending["channel_id"])
        group_public_id = _group_public_id(channel_id, conversation_id)
        collision = (
            db.query(ProjectAutomationDingTalkBinding)
            .filter(
                ProjectAutomationDingTalkBinding.public_id == group_public_id,
                ProjectAutomationDingTalkBinding.parent_id != automation_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if collision:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This DingTalk group is already bound to another automation",
            )
        binding = self._binding(db, automation_id)
        if binding is None:
            binding = ProjectAutomationDingTalkBinding(
                id=_binding_id(automation_id),
                parent_id=automation_id,
                source="dingtalk",
                status="active",
            )
            db.add(binding)
        binding.cloud_project_id = str(pending["project_id"])
        binding.public_id = group_public_id
        binding.title = conversation_title[:255]
        binding.created_by_user_id = int(pending["user_id"])
        binding.updated_by_user_id = int(pending["user_id"])
        binding.metadata_json = {
            "channel_id": channel_id,
            "conversation_id": conversation_id,
        }
        binding.version = int(binding.version or 0) + 1
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This DingTalk group is already bound to another automation",
            ) from exc
        db.refresh(binding)
        return binding

    @staticmethod
    def find_active(
        db: Session, channel_id: int, conversation_id: str
    ) -> ProjectAutomationDingTalkBinding | None:
        return (
            db.query(ProjectAutomationDingTalkBinding)
            .filter(
                ProjectAutomationDingTalkBinding.public_id
                == _group_public_id(channel_id, conversation_id),
            )
            .one_or_none()
        )

    @staticmethod
    def _binding(
        db: Session, automation_id: str
    ) -> ProjectAutomationDingTalkBinding | None:
        return (
            db.query(ProjectAutomationDingTalkBinding)
            .filter(ProjectAutomationDingTalkBinding.parent_id == automation_id)
            .one_or_none()
        )


project_automation_dingtalk_binding_service = ProjectAutomationDingTalkBindingService()
