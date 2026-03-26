# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for tolerant market subscription display with invalid trigger data."""

import uuid

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.kind import Kind
from app.models.user import User
from app.services.subscription.market_service import subscription_market_service


def _create_user(
    db: Session, username: str, email: str, is_active: bool = True
) -> User:
    user = User(
        user_name=username,
        password_hash=get_password_hash("password"),
        email=email,
        is_active=is_active,
        git_info=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_invalid_market_subscription(
    db: Session, owner_user_id: int, interval_minutes: int = 5
) -> int:
    suffix = uuid.uuid4().hex[:8]
    subscription = Kind(
        user_id=owner_user_id,
        kind="Subscription",
        name=f"invalid-market-{suffix}",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Subscription",
            "metadata": {
                "name": f"invalid-market-{suffix}",
                "namespace": "default",
            },
            "spec": {
                "displayName": "Invalid Market Subscription",
                "description": "for display tolerance",
                # Intentionally invalid to force full schema validation failure.
                "taskType": "invalid-task-type",
                "visibility": "market",
                "trigger": {
                    "type": "interval",
                    "interval": {"unit": "minutes", "value": interval_minutes},
                },
                "teamRef": {"name": "team", "namespace": "default"},
                "promptTemplate": "prompt",
            },
            "_internal": {
                "trigger_type": "interval",
                "rental_count": 2,
                "is_rental": False,
            },
        },
        is_active=True,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription.id


def test_discover_market_subscriptions_tolerates_invalid_interval_trigger(
    test_db: Session, test_user: User
):
    """Market discover should not fail on invalid interval values in CRD."""
    viewer = _create_user(
        test_db,
        username=f"viewer-{uuid.uuid4().hex[:6]}",
        email=f"viewer-{uuid.uuid4().hex[:6]}@example.com",
    )
    subscription_id = _create_invalid_market_subscription(
        test_db, owner_user_id=test_user.id, interval_minutes=5
    )

    items, total = subscription_market_service.discover_market_subscriptions(
        test_db, user_id=viewer.id, search="invalid market"
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].id == subscription_id
    assert items[0].trigger_description == "Every 5 minutes"
    assert items[0].task_type.value == "collection"


def test_get_market_subscription_detail_tolerates_invalid_interval_trigger(
    test_db: Session, test_user: User
):
    """Market detail should be available even when interval is invalid."""
    viewer = _create_user(
        test_db,
        username=f"viewer-{uuid.uuid4().hex[:6]}",
        email=f"viewer-{uuid.uuid4().hex[:6]}@example.com",
    )
    subscription_id = _create_invalid_market_subscription(
        test_db, owner_user_id=test_user.id, interval_minutes=2
    )

    detail = subscription_market_service.get_market_subscription_detail(
        test_db, subscription_id=subscription_id, user_id=viewer.id
    )

    assert detail.id == subscription_id
    assert detail.trigger_description == "Every 2 minutes"
    assert detail.task_type.value == "collection"
