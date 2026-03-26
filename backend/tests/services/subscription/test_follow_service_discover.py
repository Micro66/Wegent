# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for discover subscriptions behavior in follow service."""

import uuid

from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.user import User
from app.schemas.subscription import SubscriptionCreate, SubscriptionVisibility
from app.services.subscription.follow_service import subscription_follow_service
from app.services.subscription.service import SubscriptionService


def _create_team(db: Session, owner_user_id: int, name: str) -> Kind:
    team = Kind(
        user_id=owner_user_id,
        kind="Team",
        name=name,
        namespace="default",
        json={},
        is_active=True,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def _create_public_subscription(db: Session, owner_user_id: int, team_id: int) -> int:
    service = SubscriptionService()
    suffix = uuid.uuid4().hex[:8]
    created = service.create_subscription(
        db,
        subscription_in=SubscriptionCreate(
            name=f"public-valid-{suffix}",
            namespace="default",
            display_name="Public Valid Subscription",
            task_type="collection",
            visibility=SubscriptionVisibility.PUBLIC,
            trigger_type="cron",
            trigger_config={"expression": "0 9 * * *", "timezone": "UTC"},
            team_id=team_id,
            prompt_template="valid prompt",
        ),
        user_id=owner_user_id,
    )
    return created.id


def _create_invalid_subscription_kind(db: Session, owner_user_id: int) -> int:
    invalid_subscription = Kind(
        user_id=owner_user_id,
        kind="Subscription",
        name=f"invalid-subscription-{uuid.uuid4().hex[:8]}",
        namespace="default",
        # Intentionally malformed JSON to emulate historical dirty data.
        json={"apiVersion": "agent.wecode.io/v1", "kind": "Subscription"},
        is_active=True,
    )
    db.add(invalid_subscription)
    db.commit()
    db.refresh(invalid_subscription)
    return invalid_subscription.id


def _create_public_invalid_subscription_kind_with_recoverable_spec(
    db: Session, owner_user_id: int
) -> int:
    invalid_subscription = Kind(
        user_id=owner_user_id,
        kind="Subscription",
        name=f"invalid-public-{uuid.uuid4().hex[:8]}",
        namespace="default",
        # This is recoverable for discover:
        # - visibility and displayName are present
        # - taskType is intentionally invalid to make full schema validation fail
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Subscription",
            "metadata": {
                "name": f"invalid-public-{uuid.uuid4().hex[:8]}",
                "namespace": "default",
            },
            "spec": {
                "displayName": "Fallback Visible Subscription",
                "description": "recoverable invalid schema for discover",
                "visibility": "public",
                "taskType": "invalid-task-type",
                "trigger": {
                    "type": "cron",
                    "cron": {"expression": "0 9 * * *", "timezone": "UTC"},
                },
                "teamRef": {"name": "team", "namespace": "default"},
                "promptTemplate": "prompt",
            },
        },
        is_active=True,
    )
    db.add(invalid_subscription)
    db.commit()
    db.refresh(invalid_subscription)
    return invalid_subscription.id


def test_discover_subscriptions_skips_unrecoverable_invalid_crd_records(
    test_db: Session, test_user: User
):
    """Discover should skip malformed subscription CRDs instead of raising 500."""
    team = _create_team(test_db, test_user.id, name=f"team-{uuid.uuid4().hex[:6]}")
    valid_subscription_id = _create_public_subscription(test_db, test_user.id, team.id)
    _create_invalid_subscription_kind(test_db, test_user.id)

    response = subscription_follow_service.discover_subscriptions(
        test_db,
        user_id=test_user.id,
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].id == valid_subscription_id


def test_discover_subscriptions_includes_recoverable_public_invalid_crd(
    test_db: Session, test_user: User
):
    """Discover should include public invalid CRDs when required fields are recoverable."""
    invalid_subscription_id = (
        _create_public_invalid_subscription_kind_with_recoverable_spec(
            test_db, test_user.id
        )
    )

    response = subscription_follow_service.discover_subscriptions(
        test_db,
        user_id=test_user.id,
        search="fallback visible",
    )

    assert response.total == 1
    assert len(response.items) == 1
    assert response.items[0].id == invalid_subscription_id
