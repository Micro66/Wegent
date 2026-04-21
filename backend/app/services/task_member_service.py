# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Service for task member (group chat) management.

Uses the unified ResourceMember model instead of the legacy TaskMember table.
"""

import copy
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.kind import Kind
from app.models.resource_member import (
    EPOCH_TIME,
    MemberStatus,
    ResourceMember,
    ResourceRole,
)
from app.models.share_link import ResourceType
from app.models.task import TaskResource
from app.models.user import User
from app.schemas.task_member import MemberStatus as SchemaMemberStatus
from app.schemas.task_member import (
    TaskMemberListResponse,
    TaskMemberResponse,
)
from app.services.chat.group_chat_config import (
    DEFAULT_GROUP_CHAT_HISTORY_WINDOW,
    get_group_chat_team_refs,
)

logger = logging.getLogger(__name__)


class TaskMemberService:
    """Service for managing group chat members using ResourceMember."""

    def get_task(self, db: Session, task_id: int) -> Optional[TaskResource]:
        """Get a task by ID (including subscription tasks)"""
        return (
            db.query(TaskResource)
            .filter(
                TaskResource.id == task_id,
                TaskResource.kind == "Task",
                TaskResource.is_active.in_(TaskResource.is_active_query()),
            )
            .first()
        )

    def get_user(self, db: Session, user_id: int) -> Optional[User]:
        """Get a user by ID"""
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()

    def get_task_owner_id(self, db: Session, task_id: int) -> Optional[int]:
        """Get the owner (creator) user_id of a task"""
        task = self.get_task(db, task_id)
        if task:
            return task.user_id
        return None

    def is_task_owner(self, db: Session, task_id: int, user_id: int) -> bool:
        """Check if a user is the owner of a task"""
        task = self.get_task(db, task_id)
        return task is not None and task.user_id == user_id

    def is_member(self, db: Session, task_id: int, user_id: int) -> bool:
        """Check if a user is an active member of a task"""
        # Task owner is always considered a member
        if self.is_task_owner(db, task_id, user_id):
            return True

        # Check ResourceMember for approved status
        # Exclude share records (copied_resource_id > 0), only consider actual group chat members
        member = (
            db.query(ResourceMember)
            .filter(
                ResourceMember.resource_type == ResourceType.TASK,
                ResourceMember.resource_id == task_id,
                ResourceMember.user_id == user_id,
                ResourceMember.status == MemberStatus.APPROVED,
                ResourceMember.copied_resource_id == 0,
            )
            .first()
        )
        return member is not None

    def is_group_chat(self, db: Session, task_id: int) -> bool:
        """Check if a task is configured as a group chat"""
        logger.info(f"[is_group_chat] Checking task_id={task_id}")
        task = self.get_task(db, task_id)
        if not task:
            logger.warning(f"[is_group_chat] Task {task_id} not found")
            return False

        task_json = task.json if isinstance(task.json, dict) else {}
        logger.info(
            f"[is_group_chat] task_id={task_id}, task_json type={type(task.json)}, is_dict={isinstance(task.json, dict)}"
        )
        spec = task_json.get("spec", {})
        is_group_chat = spec.get("is_group_chat", False)
        logger.info(
            f"[is_group_chat] task_id={task_id}, is_group_chat={is_group_chat}, spec={spec}"
        )
        return is_group_chat

    def convert_to_group_chat(
        self,
        db: Session,
        task_id: int,
        team_refs: Optional[List[dict]] = None,
        history_window: Optional[dict] = None,
    ) -> bool:
        """Convert an existing task to a group chat or update its configuration."""
        task = self.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get current task JSON - use deep copy to avoid modifying the original
        task_json = copy.deepcopy(task.json) if isinstance(task.json, dict) else {}
        spec = task_json.get("spec", {})
        existing_team_ref = spec.get("teamRef")
        logger.info("[convert_to_group_chat] Input team_refs: %s", team_refs)
        normalized_team_refs = [
            team_ref
            for team_ref in (team_refs or get_group_chat_team_refs(task_json))
            if isinstance(team_ref, dict)
        ]
        logger.info(
            "[convert_to_group_chat] Normalized team_refs: %s", normalized_team_refs
        )
        if not normalized_team_refs and isinstance(existing_team_ref, dict):
            normalized_team_refs = [existing_team_ref]

        if not normalized_team_refs:
            raise HTTPException(
                status_code=400,
                detail="At least one agent must be configured for the group chat",
            )

        normalized_history_window = {
            "maxDays": int(
                (history_window or {}).get(
                    "maxDays", DEFAULT_GROUP_CHAT_HISTORY_WINDOW["maxDays"]
                )
            ),
            "maxMessages": int(
                (history_window or {}).get(
                    "maxMessages", DEFAULT_GROUP_CHAT_HISTORY_WINDOW["maxMessages"]
                )
            ),
        }

        spec["is_group_chat"] = True
        spec["teamRef"] = normalized_team_refs[0]
        spec["teamRefs"] = normalized_team_refs
        spec["groupChatConfig"] = {"historyWindow": normalized_history_window}

        logger.info(
            "[convert_to_group_chat] Saving team_refs: %s", normalized_team_refs
        )
        task_json["spec"] = spec

        # IMPORTANT: Mark the json field as modified so SQLAlchemy detects the change
        logger.info("[convert_to_group_chat] task_json before save: %s", task_json)
        logger.info(
            "[convert_to_group_chat] task_json type: %s, spec type: %s, teamRefs type: %s",
            type(task_json),
            type(task_json.get("spec")),
            type(task_json.get("spec", {}).get("teamRefs")),
        )
        task.json = task_json
        logger.info("[convert_to_group_chat] task.json assigned: %s", task.json)
        flag_modified(task, "json")

        # Sync to physical column for optimized queries
        task.is_group_chat = True

        task.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(task)

        # Verify what was actually saved to database
        saved_json = task.json if isinstance(task.json, dict) else {}
        saved_spec = saved_json.get("spec", {})
        saved_team_refs = saved_spec.get("teamRefs", [])
        logger.info(
            "[convert_to_group_chat] After commit - saved teamRefs: %s", saved_team_refs
        )
        logger.info(
            "[convert_to_group_chat] After commit - task.json type: %s", type(task.json)
        )

        logger.info(
            "Task %s converted to group chat with %s team refs",
            task_id,
            len(normalized_team_refs),
        )
        return True

    def get_member_count(self, db: Session, task_id: int) -> int:
        """Get the number of active members in a task (including owner)"""
        # Exclude share records (copied_resource_id > 0), only count actual group chat members
        member_count = (
            db.query(ResourceMember)
            .filter(
                ResourceMember.resource_type == ResourceType.TASK,
                ResourceMember.resource_id == task_id,
                ResourceMember.status == MemberStatus.APPROVED,
                ResourceMember.copied_resource_id == 0,
            )
            .count()
        )
        # Add 1 for the task owner
        return member_count + 1

    def get_members(self, db: Session, task_id: int) -> TaskMemberListResponse:
        """Get all active members of a task"""
        task = self.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        task_owner_id = task.user_id

        # Get task owner info
        owner = self.get_user(db, task_owner_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Task owner not found")

        # Build member list, starting with owner
        members = []

        # Add owner as first member
        owner_member = TaskMemberResponse(
            id=0,  # Special ID for owner
            task_id=task_id,
            user_id=task_owner_id,
            username=owner.user_name,
            avatar=None,  # Add avatar field if exists in User model
            invited_by=task_owner_id,
            inviter_name=owner.user_name,
            status=SchemaMemberStatus.ACTIVE,
            joined_at=task.created_at,
            is_owner=True,
        )
        members.append(owner_member)

        # Get other members from ResourceMember
        # Exclude share records (copied_resource_id > 0), only get actual group chat members
        task_members = (
            db.query(ResourceMember)
            .filter(
                ResourceMember.resource_type == ResourceType.TASK,
                ResourceMember.resource_id == task_id,
                ResourceMember.status == MemberStatus.APPROVED,
                ResourceMember.copied_resource_id == 0,
            )
            .all()
        )

        for tm in task_members:
            user = self.get_user(db, tm.user_id)
            inviter = (
                self.get_user(db, tm.invited_by_user_id)
                if tm.invited_by_user_id > 0
                else None
            )

            if user:
                member = TaskMemberResponse(
                    id=tm.id,
                    task_id=task_id,
                    user_id=tm.user_id,
                    username=user.user_name,
                    avatar=None,
                    invited_by=tm.invited_by_user_id,
                    inviter_name=inviter.user_name if inviter else "Unknown",
                    status=SchemaMemberStatus.ACTIVE,
                    joined_at=tm.requested_at,
                    is_owner=False,
                )
                members.append(member)

        return TaskMemberListResponse(
            members=members,
            total=len(members),
            task_owner_id=task_owner_id,
        )

    def add_member(
        self,
        db: Session,
        task_id: int,
        user_id: int,
        invited_by: int,
    ) -> ResourceMember:
        """Add a user as a member to a task"""
        logger.info(
            f"[add_member] Adding member: task_id={task_id}, user_id={user_id}, invited_by={invited_by}"
        )

        # Check if user already exists (even if rejected)
        existing = (
            db.query(ResourceMember)
            .filter(
                ResourceMember.resource_type == ResourceType.TASK,
                ResourceMember.resource_id == task_id,
                ResourceMember.user_id == user_id,
            )
            .first()
        )

        if existing:
            logger.info(
                f"[add_member] Existing member found: id={existing.id}, status={existing.status}"
            )
            if existing.status == MemberStatus.APPROVED:
                logger.warning(
                    f"[add_member] User {user_id} is already a member of task {task_id}"
                )
                raise HTTPException(status_code=400, detail="User is already a member")
            # Reactivate rejected/pending member
            logger.info(
                f"[add_member] Reactivating member: id={existing.id}, old_status={existing.status}"
            )
            existing.status = MemberStatus.APPROVED
            existing.invited_by_user_id = invited_by
            existing.requested_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
            existing.role = (
                ResourceRole.Maintainer.value
            )  # Group chat members get maintainer role
            # Clear stale review metadata from previous rejection
            existing.reviewed_by_user_id = 0
            existing.reviewed_at = EPOCH_TIME
            db.commit()
            db.refresh(existing)
            logger.info(
                f"[add_member] Member reactivated successfully: id={existing.id}"
            )
            return existing

        # Create new member
        logger.info(
            f"[add_member] Creating new member for task {task_id}, user {user_id}"
        )
        new_member = ResourceMember(
            resource_type=ResourceType.TASK,
            resource_id=task_id,
            user_id=user_id,
            role=ResourceRole.Maintainer.value,  # Group chat members get maintainer role
            status=MemberStatus.APPROVED,
            invited_by_user_id=invited_by,
            share_link_id=0,
            reviewed_by_user_id=0,
            copied_resource_id=0,
            requested_at=datetime.utcnow(),
        )
        db.add(new_member)
        db.commit()
        db.refresh(new_member)
        logger.info(f"[add_member] New member created successfully: id={new_member.id}")
        return new_member

    def remove_member(
        self,
        db: Session,
        task_id: int,
        user_id: int,
        removed_by: int,
    ) -> bool:
        """Remove a member from a task (soft delete by setting status to rejected)"""
        # Cannot remove the task owner
        if self.is_task_owner(db, task_id, user_id):
            raise HTTPException(status_code=400, detail="Cannot remove the task owner")

        member = (
            db.query(ResourceMember)
            .filter(
                ResourceMember.resource_type == ResourceType.TASK,
                ResourceMember.resource_id == task_id,
                ResourceMember.user_id == user_id,
                ResourceMember.status == MemberStatus.APPROVED,
            )
            .first()
        )

        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        member.status = MemberStatus.REJECTED
        member.reviewed_by_user_id = removed_by
        member.reviewed_at = datetime.utcnow()
        member.updated_at = datetime.utcnow()
        db.commit()

        return True

    def get_team_id(self, db: Session, task_id: int) -> Optional[int]:
        """Get the team ID associated with a task"""
        task = self.get_task(db, task_id)
        if not task:
            return None

        try:
            task_json = task.json if isinstance(task.json, dict) else {}
            spec = task_json.get("spec", {})
            team_ref = spec.get("teamRef", {})
            team_name = team_ref.get("name")
            team_namespace = team_ref.get("namespace", "default")

            if team_name:
                # Get the team Kind to get its ID
                team = (
                    db.query(Kind)
                    .filter(
                        Kind.name == team_name,
                        Kind.namespace == team_namespace,
                        Kind.kind == "Team",
                        Kind.is_active == True,
                    )
                    .first()
                )
                if team:
                    return team.id
        except Exception as e:
            logger.warning(f"Failed to get team ID: {e}")

        return None

    def get_team_name(self, db: Session, task_id: int) -> Optional[str]:
        """Get the team name associated with a task"""
        task = self.get_task(db, task_id)
        if not task:
            return None

        try:
            task_json = task.json if isinstance(task.json, dict) else {}
            spec = task_json.get("spec", {})
            team_ref = spec.get("teamRef", {})
            team_name = team_ref.get("name")
            team_namespace = team_ref.get("namespace", "default")

            if team_name:
                # Get the team Kind to get its display name
                team = (
                    db.query(Kind)
                    .filter(
                        Kind.name == team_name,
                        Kind.namespace == team_namespace,
                        Kind.kind == "Team",
                        Kind.is_active == True,
                    )
                    .first()
                )
                if team:
                    team_json = team.json if isinstance(team.json, dict) else {}
                    team_spec = team_json.get("spec", {})
                    return team_spec.get("displayName", team_name)
                return team_name
        except Exception as e:
            logger.warning(f"Failed to get team name: {e}")

        return None


task_member_service = TaskMemberService()
