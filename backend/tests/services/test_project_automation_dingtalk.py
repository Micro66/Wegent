# SPDX-FileCopyrightText: 2026 Weibo, Inc.
# SPDX-License-Identifier: Apache-2.0

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.delivery import (
    CloudProject,
    LoopItem,
    ProjectAutomationRule,
    ProjectAutomationRun,
    ProjectIncomingEvent,
)
from app.services.channels.dingtalk.sender import DingTalkRobotSender
from app.services.loop_items.provider_router import RoutedLoopItem
from app.services.project_automation_dingtalk import (
    DingTalkIssueInput,
    DingTalkMedia,
    ProjectAutomationDingTalkIngress,
    _display_time,
    parse_dingtalk_issue,
)
from app.services.project_automation_dingtalk_binding import (
    project_automation_dingtalk_binding_service,
)
from app.services.project_automation_domain import ProjectAutomationEvent
from app.services.project_automation_execution import (
    ProjectAutomationProcessor,
    project_automation_execution,
)


def test_parse_direct_text_message() -> None:
    parsed = parse_dingtalk_issue(
        {
            "senderNick": "Alice",
            "createdAt": 1,
            "text": {"content": "Login is broken\nwhen SSO is enabled"},
        }
    )

    assert parsed.problem == "Login is broken\nwhen SSO is enabled"
    assert parsed.supplemental == ""
    assert parsed.original_author == "Alice"


def test_parse_quoted_text_and_supplement() -> None:
    parsed = parse_dingtalk_issue(
        {
            "senderNick": "Bob",
            "text": {
                "content": "This affects production",
                "repliedMsg": {
                    "senderNick": "Alice",
                    "createdAt": 100,
                    "content": {"text": "Login is broken"},
                },
            },
        }
    )

    assert parsed.problem == "Login is broken"
    assert parsed.supplemental == "This affects production"
    assert parsed.original_author == "Alice"
    assert parsed.original_time == "100"


def test_parse_quoted_rich_text_collects_all_images_and_text() -> None:
    parsed = parse_dingtalk_issue(
        {
            "text": {
                "content": "please handle",
                "repliedMsg": {
                    "msgType": "richText",
                    "content": {
                        "richText": [
                            {"text": "First line"},
                            {"downloadCode": "image-a"},
                            {"text": "Second line", "downloadCode": "image-b"},
                        ]
                    },
                },
            }
        }
    )

    assert parsed.problem == "First line\nSecond line"
    assert [item.download_code for item in parsed.media] == ["image-a", "image-b"]


def test_parse_direct_rich_text_uses_text_and_media() -> None:
    parsed = parse_dingtalk_issue(
        {
            "msgtype": "richText",
            "content": {
                "richText": [
                    {"text": "First line"},
                    {"downloadCode": "image-a", "type": "picture"},
                    {"text": "Second line"},
                ]
            },
            "senderNick": "Reporter",
            "createAt": 1720000000000,
        }
    )

    assert parsed.problem == "First line\nSecond line"
    assert parsed.supplemental == ""
    assert [item.download_code for item in parsed.media] == ["image-a"]


def test_parse_replied_content_accepts_serialized_payload() -> None:
    parsed = parse_dingtalk_issue(
        {
            "text": {
                "content": "supplement",
                "repliedMsg": {
                    "content": '{"text":"quoted problem"}',
                    "senderId": "quoted-user-id",
                },
            }
        }
    )

    assert parsed.problem == "quoted problem"
    assert parsed.supplemental == "supplement"
    assert parsed.original_author == "quoted-user-id"


def test_parse_self_quote_uses_outer_sender_nickname() -> None:
    parsed = parse_dingtalk_issue(
        {
            "senderNick": "Alice",
            "senderStaffId": "alice-id",
            "text": {
                "content": "please handle",
                "repliedMsg": {
                    "content": {"text": "quoted problem"},
                    "senderId": "alice-id",
                },
            },
        }
    )

    assert parsed.original_author == "Alice"


def test_display_time_converts_dingtalk_milliseconds() -> None:
    displayed = _display_time("1788406882815")

    assert displayed.startswith("2026-09-03T")
    assert displayed != "1788406882815"


def _add_rule(db: Session, project_id: str, automation_id: str) -> None:
    if db.get(CloudProject, project_id) is None:
        db.add(CloudProject(id=project_id, title="Project"))
        db.flush()
    db.add(
        ProjectAutomationRule(
            id=automation_id,
            cloud_project_id=project_id,
            title="Automation",
            status="enabled",
        )
    )
    db.commit()


def test_binding_reuses_loop_item_and_atomically_replaces_group(
    test_db: Session,
) -> None:
    _add_rule(test_db, "project-a", "automation-a")
    pending = {
        "automation_id": "automation-a",
        "project_id": "project-a",
        "channel_id": 17,
        "user_id": 9,
    }

    first = project_automation_dingtalk_binding_service.bind(
        test_db, pending, "group-a", "First group"
    )
    second = project_automation_dingtalk_binding_service.bind(
        test_db, pending, "group-b", "Second group"
    )

    assert first.id == second.id
    assert second.resource_type == "automation_dt_binding"
    assert second.parent_id == "automation-a"
    assert second.cloud_project_id == "project-a"
    assert second.conversation_title == "Second group"
    assert second.channel_id == 17
    assert second.conversation_id == "group-b"
    assert (
        project_automation_dingtalk_binding_service.find_active(test_db, 17, "group-a")
        is None
    )
    assert (
        project_automation_dingtalk_binding_service.find_active(
            test_db, 17, "group-b"
        ).id
        == second.id
    )


def test_robot_group_can_only_bind_one_rule(test_db: Session) -> None:
    _add_rule(test_db, "project-b", "automation-b1")
    _add_rule(test_db, "project-b", "automation-b2")
    base = {"project_id": "project-b", "channel_id": 23, "user_id": 9}
    project_automation_dingtalk_binding_service.bind(
        test_db,
        {**base, "automation_id": "automation-b1"},
        "shared-group",
        "Shared group",
    )

    with pytest.raises(HTTPException) as error:
        project_automation_dingtalk_binding_service.bind(
            test_db,
            {**base, "automation_id": "automation-b2"},
            "shared-group",
            "Shared group",
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_media_staging_is_all_or_nothing() -> None:
    ingress = ProjectAutomationDingTalkIngress()
    download = AsyncMock(
        side_effect=[(b"first", "image/png"), RuntimeError("download failed")]
    )

    with (
        patch(
            "app.services.project_automation_dingtalk.delivery_storage.put_bytes"
        ) as put_bytes,
        patch(
            "app.services.project_automation_dingtalk.delivery_storage.remove_objects"
        ) as remove_objects,
    ):
        with pytest.raises(RuntimeError, match="download failed"):
            await ingress._stage_media(
                SimpleNamespace(public_id="project-media"),
                SimpleNamespace(public_id="event-media"),
                (
                    DingTalkMedia("first-code", "first.png"),
                    DingTalkMedia("second-code", "second.png"),
                ),
                download,
            )

    put_bytes.assert_called_once()
    remove_objects.assert_called_once_with(
        ["projects/project-media/incoming/dingtalk/event-media/1"]
    )


@pytest.mark.asyncio
async def test_bound_group_rejects_submitter_without_developer_role() -> None:
    sender = MagicMock()
    sender.reply_text_emotion = AsyncMock(return_value=True)
    with (
        patch.object(
            project_automation_dingtalk_binding_service,
            "find_active",
            return_value=SimpleNamespace(project_id="project-denied"),
        ),
        patch(
            "app.services.project_automation_dingtalk.require_cloud_project_role",
            side_effect=HTTPException(403, "Insufficient permission"),
        ),
    ):
        handled = await ProjectAutomationDingTalkIngress().handle(
            MagicMock(),
            channel_id=31,
            callback={"conversationId": "group", "msgId": "message"},
            user=SimpleNamespace(id=10),
            is_group=True,
            is_mention=True,
            download=AsyncMock(),
            robot_sender=sender,
        )

    assert handled is True
    sender.reply_text_emotion.assert_awaited_once_with("message", "group", "无项目权限")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["local", "github", "gitlab"])
async def test_ingress_creates_issue_through_every_supported_provider(
    test_db: Session,
    provider: str,
) -> None:
    project = CloudProject(
        id=f"project-{provider}",
        public_id=f"project-{provider}",
        title="Project",
        metadata_json={"task_provider": provider},
    )
    rule = ProjectAutomationRule(
        id=f"automation-{provider}",
        cloud_project_id=project.id,
        title="Automation",
        status="enabled",
        metadata_json={
            "trigger_type": "event",
            "event_type": "task.created",
            "event_source": "dingtalk",
        },
    )
    event = ProjectIncomingEvent(
        id=f"event-{provider}",
        public_id=str(uuid.uuid4()),
        cloud_project_id=project.id,
        parent_id=rule.id,
        source="dingtalk",
        status="processing",
    )
    item = LoopItem(
        id=f"issue-{provider}",
        cloud_project_id=project.id,
        title="Provider issue",
        description="Description",
        status="todo",
        priority="medium",
        metadata_json={"tags": []},
    )
    test_db.add_all([project, rule, event, item])
    test_db.commit()
    routed = RoutedLoopItem(values={"id": item.id}, internal_item=item)

    with (
        patch(
            "app.services.project_automation_dingtalk.external_loop_item_provider.list",
            return_value=[],
        ),
        patch(
            "app.services.project_automation_dingtalk.loop_item_provider_router.create",
            return_value=routed,
        ) as create,
        patch(
            "app.services.project_automation_dingtalk.project_automation_processor.process",
            new=AsyncMock(return_value=1),
        ) as process,
    ):
        await ProjectAutomationDingTalkIngress()._create_and_dispatch(
            test_db,
            project,
            rule,
            event,
            SimpleNamespace(id=42, user_name="reporter"),
            {"conversationTitle": "Feedback", "senderNick": "Reporter"},
            DingTalkIssueInput(
                problem="Provider issue",
                supplemental="",
                original_author="Reporter",
                original_time="",
                media=(),
            ),
            [],
        )

    create.assert_called_once()
    process.assert_awaited_once()
    assert event.loop_item_id == item.id
    assert event.status == "dispatched"


@pytest.mark.asyncio
async def test_received_reaction_failure_keeps_event_recoverable() -> None:
    event = SimpleNamespace(status="dispatched")
    sender = DingTalkRobotSender("client", "secret")
    sender.reply_text_emotion = AsyncMock(return_value=False)
    db = MagicMock()

    with pytest.raises(RuntimeError, match="text tag was not accepted: 收到"):
        await ProjectAutomationDingTalkIngress._ack(
            event,
            {"msgId": "message", "conversationId": "group"},
            sender,
            db,
        )

    assert event.status == "dispatched"
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_sender_builds_received_text_emotion_request() -> None:
    sender = DingTalkRobotSender("robot-code", "secret")
    sender._get_access_token = AsyncMock(return_value="access-token")
    client = MagicMock()
    client.robot_reply_emotion_with_options_async = AsyncMock()

    with patch("alibabacloud_dingtalk.robot_1_0.client.Client", return_value=client):
        accepted = await sender.reply_text_emotion("message-id", "group-id", "收到")

    assert accepted is True
    request, headers, _runtime = (
        client.robot_reply_emotion_with_options_async.await_args.args
    )
    assert request.robot_code == "robot-code"
    assert request.open_msg_id == "message-id"
    assert request.open_conversation_id == "group-id"
    assert request.text_emotion.text == "收到"
    assert headers.x_acs_dingtalk_access_token == "access-token"


@pytest.mark.asyncio
async def test_incoming_event_dispatch_creates_one_durable_run(
    test_db: Session,
) -> None:
    test_db.add(CloudProject(id="project-c", public_id="project-c", title="Project"))
    test_db.add(
        ProjectAutomationRule(
            id="automation-c",
            cloud_project_id="project-c",
            title="Automation",
            status="enabled",
            metadata_json={
                "trigger_type": "event",
                "event_type": "task.created",
                "event_source": "dingtalk",
            },
        )
    )
    test_db.commit()
    event = ProjectAutomationEvent(
        event_type="task.created",
        project_id="project-c",
        subject_id="issue-c",
        source="dingtalk",
        actor_user_id=9,
        payload={"title": "Issue", "incoming_event_id": "incoming-c"},
    )

    async def mark_queued(_db, _rule, run) -> None:
        run.status = "queued"
        _db.commit()

    with (
        patch.object(
            project_automation_execution,
            "dispatch",
            new=AsyncMock(side_effect=mark_queued),
        ) as dispatch,
        patch(
            "app.tasks.robot_queue_tasks.consume_queues_background",
            new=AsyncMock(),
        ),
    ):
        processor = ProjectAutomationProcessor()
        assert (
            await processor.process(test_db, event, automation_id="automation-c") == 1
        )
        assert (
            await processor.process(test_db, event, automation_id="automation-c") == 1
        )

    assert dispatch.await_count == 1
    assert (
        test_db.query(ProjectAutomationRun)
        .filter(ProjectAutomationRun.parent_id == "automation-c")
        .count()
        == 1
    )
