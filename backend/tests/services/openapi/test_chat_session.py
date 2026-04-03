# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.kind import Kind
from app.models.user import User


@pytest.fixture
def openapi_team(test_db: Session, test_user: User) -> Kind:
    """Create a Team for chat session setup tests."""
    team = Kind(
        user_id=test_user.id,
        kind="Team",
        name="session-team",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Team",
            "metadata": {"name": "session-team", "namespace": "default"},
            "spec": {
                "collaborationModel": "sequential",
                "members": [
                    {
                        "botRef": {"name": "session-bot", "namespace": "default"},
                        "role": "worker",
                    }
                ],
            },
        },
        is_active=True,
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture
def openapi_bot(test_db: Session, test_user: User) -> Kind:
    """Create a Bot referenced by the Team."""
    bot = Kind(
        user_id=test_user.id,
        kind="Bot",
        name="session-bot",
        namespace="default",
        json={
            "apiVersion": "agent.wecode.io/v1",
            "kind": "Bot",
            "metadata": {"name": "session-bot", "namespace": "default"},
            "spec": {},
        },
        is_active=True,
    )
    test_db.add(bot)
    test_db.commit()
    test_db.refresh(bot)
    return bot


@pytest.mark.unit
def test_setup_chat_session_marks_failed_before_raising_validation_error(
    test_db: Session,
    test_user: User,
    openapi_team: Kind,
    openapi_bot: Kind,
):
    """OpenAPI session setup should fail the task instead of leaving it pending."""
    from app.models.subtask import Subtask, SubtaskStatus
    from app.services.openapi.chat_session import setup_chat_session

    mock_builder = MagicMock()
    mock_builder.build.side_effect = ValueError(
        "Bot developer-bot has no model configured"
    )

    with (
        patch("app.services.execution.TaskRequestBuilder", return_value=mock_builder),
        pytest.raises(HTTPException, match="no model configured") as exc_info,
    ):
        setup_chat_session(
            db=test_db,
            user=test_user,
            team=openapi_team,
            model_info={},
            input_text="hello",
            tool_settings={},
        )

    test_db.expire_all()
    assistant_subtask = test_db.query(Subtask).order_by(Subtask.id.desc()).first()

    assert exc_info.value.status_code == 400
    assert assistant_subtask is not None
    assert assistant_subtask.status == SubtaskStatus.FAILED
    assert (
        assistant_subtask.error_message == "Bot developer-bot has no model configured"
    )
