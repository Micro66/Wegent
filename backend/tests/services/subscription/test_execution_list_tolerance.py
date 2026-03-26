# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for tolerant execution listing with invalid subscription CRD data."""

import uuid

from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.subscription import BackgroundExecution
from app.models.user import User
from app.services.subscription.execution import background_execution_manager


def _create_invalid_public_subscription(db: Session, owner_user_id: int) -> int:
    suffix = uuid.uuid4().hex[:8]
    subscription = Kind(
        user_id=owner_user_id,
        kind="Subscription",
        name=f"invalid-timeline-{suffix}",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Subscription",
            "metadata": {
                "name": f"invalid-timeline-{suffix}",
                "namespace": "default",
            },
            "spec": {
                "displayName": "Invalid Timeline Subscription",
                "description": "for execution listing tolerance",
                # Intentionally invalid to force schema validation failure.
                "taskType": "invalid-task-type",
                "visibility": "public",
                "trigger": {
                    "type": "interval",
                    "interval": {"unit": "minutes", "value": 5},
                },
                "teamRef": {"name": "team", "namespace": "default"},
                "promptTemplate": "prompt",
            },
        },
        is_active=True,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription.id


def _create_execution(db: Session, user_id: int, subscription_id: int) -> int:
    execution = BackgroundExecution(
        user_id=user_id,
        subscription_id=subscription_id,
        task_id=0,
        trigger_type="manual",
        trigger_reason="test",
        prompt="prompt",
        status="COMPLETED",
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution.id


def test_list_executions_tolerates_invalid_subscription_crd_with_subscription_filter(
    test_db: Session, test_user: User
):
    """list_executions should not crash when filtered public subscription is invalid."""
    subscription_id = _create_invalid_public_subscription(test_db, test_user.id)
    execution_id = _create_execution(test_db, test_user.id, subscription_id)

    items, total = background_execution_manager.list_executions(
        test_db,
        user_id=test_user.id,
        subscription_id=subscription_id,
    )

    assert total == 1
    assert len(items) == 1
    assert items[0].id == execution_id
    assert items[0].subscription_display_name == "Invalid Timeline Subscription"
    assert items[0].task_type == "collection"


def test_get_execution_tolerates_invalid_subscription_crd(
    test_db: Session, test_user: User
):
    """get_execution should return display fields even when subscription CRD is invalid."""
    subscription_id = _create_invalid_public_subscription(test_db, test_user.id)
    execution_id = _create_execution(test_db, test_user.id, subscription_id)

    execution = background_execution_manager.get_execution(
        test_db,
        execution_id=execution_id,
        user_id=test_user.id,
    )

    assert execution.id == execution_id
    assert execution.subscription_display_name == "Invalid Timeline Subscription"
    assert execution.task_type == "collection"
