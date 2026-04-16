# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""API tests for user IM channel bindings."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.endpoints.users import router
from app.core import security
from app.models.kind import Kind
from app.models.user import User
from app.schemas.im_channel import IMGroupBinding


@pytest.fixture
def im_bindings_client(test_db: Session, test_user: User) -> TestClient:
    """Create a focused test client for IM bindings endpoints."""

    app = FastAPI()
    app.include_router(router, prefix="/api/users")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[security.get_current_user] = lambda: test_user

    return TestClient(app)


@pytest.fixture
def sample_messager_channel(test_db: Session) -> Kind:
    """Create a sample Messager channel for testing.

    Messager channels are system-level resources with user_id=0.
    """
    channel = Kind(
        user_id=0,  # System-level resource
        name="Test DingTalk Channel",
        namespace="default",
        kind="Messager",
        json={
            "channelType": "dingtalk",
            "isEnabled": True,
            "config": {"client_id": "test_id"},
        },
    )
    test_db.add(channel)
    test_db.commit()
    test_db.refresh(channel)
    return channel


@pytest.mark.api
class TestGetIMBindings:
    """Tests for GET /me/im-bindings endpoint."""

    def test_get_im_bindings_empty(self, im_bindings_client: TestClient):
        """Test getting bindings when user has no bindings."""
        response = im_bindings_client.get("/api/users/me/im-bindings")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_im_bindings_with_data(
        self,
        im_bindings_client: TestClient,
        test_db: Session,
        test_user: User,
        sample_messager_channel: Kind,
    ):
        """Test getting bindings with existing data."""
        # Set up user preferences with bindings
        test_user.preferences = json.dumps(
            {
                "im_channels": {
                    str(sample_messager_channel.id): {
                        "channel_type": "dingtalk",
                        "private_team_id": 100,
                        "group_bindings": [
                            {
                                "conversation_id": "cid_abc123",
                                "group_name": "Test Group",
                                "team_id": 200,
                                "bound_at": "2026-04-16T10:00:00+00:00",
                            }
                        ],
                    }
                }
            }
        )
        test_db.commit()

        response = im_bindings_client.get("/api/users/me/im-bindings")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["channel_id"] == sample_messager_channel.id
        assert data[0]["channel_name"] == "Test DingTalk Channel"
        assert data[0]["channel_type"] == "dingtalk"
        assert data[0]["private_team_id"] == 100
        assert len(data[0]["group_bindings"]) == 1
        assert data[0]["group_bindings"][0]["conversation_id"] == "cid_abc123"


@pytest.mark.api
class TestUpdateIMBinding:
    """Tests for PUT /me/im-bindings/{channel_id} endpoint."""

    def test_update_private_team_id(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test updating private team ID."""
        response = im_bindings_client.put(
            f"/api/users/me/im-bindings/{sample_messager_channel.id}",
            json={"private_team_id": 123},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["channel_id"] == sample_messager_channel.id
        assert data["private_team_id"] == 123

    def test_update_add_group_binding(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test adding a group binding."""
        response = im_bindings_client.put(
            f"/api/users/me/im-bindings/{sample_messager_channel.id}",
            json={
                "group": {
                    "conversation_id": "cid_new123",
                    "group_name": "New Group",
                    "team_id": 300,
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["group_bindings"]) == 1
        assert data["group_bindings"][0]["conversation_id"] == "cid_new123"
        assert data["group_bindings"][0]["group_name"] == "New Group"
        assert data["group_bindings"][0]["team_id"] == 300

    def test_update_binding_channel_not_found(
        self,
        im_bindings_client: TestClient,
    ):
        """Test updating binding for non-existent channel."""
        response = im_bindings_client.put(
            "/api/users/me/im-bindings/99999",
            json={"private_team_id": 123},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_binding_both_private_and_group(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test updating both private team and group binding in one request."""
        response = im_bindings_client.put(
            f"/api/users/me/im-bindings/{sample_messager_channel.id}",
            json={
                "private_team_id": 456,
                "group": {
                    "conversation_id": "cid_multi",
                    "group_name": "Multi Update Group",
                    "team_id": 789,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["private_team_id"] == 456
        assert len(data["group_bindings"]) == 1
        assert data["group_bindings"][0]["conversation_id"] == "cid_multi"


@pytest.mark.api
class TestDeleteGroupBinding:
    """Tests for DELETE /me/im-bindings/{channel_id}/groups/{conversation_id} endpoint."""

    def test_delete_group_binding(
        self,
        im_bindings_client: TestClient,
        test_db: Session,
        test_user: User,
        sample_messager_channel: Kind,
    ):
        """Test removing a group binding."""
        # Set up user with a group binding
        test_user.preferences = json.dumps(
            {
                "im_channels": {
                    str(sample_messager_channel.id): {
                        "channel_type": "dingtalk",
                        "private_team_id": 100,
                        "group_bindings": [
                            {
                                "conversation_id": "cid_delete_me",
                                "group_name": "Delete Me Group",
                                "team_id": 200,
                                "bound_at": "2026-04-16T10:00:00+00:00",
                            }
                        ],
                    }
                }
            }
        )
        test_db.commit()

        response = im_bindings_client.delete(
            f"/api/users/me/im-bindings/{sample_messager_channel.id}/groups/cid_delete_me"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["group_bindings"]) == 0

    def test_delete_nonexistent_group_binding(
        self,
        im_bindings_client: TestClient,
        test_db: Session,
        test_user: User,
        sample_messager_channel: Kind,
    ):
        """Test removing a non-existent group binding."""
        # Set up user with no bindings
        test_user.preferences = json.dumps({"im_channels": {}})
        test_db.commit()

        response = im_bindings_client.delete(
            f"/api/users/me/im-bindings/{sample_messager_channel.id}/groups/cid_nonexistent"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.api
class TestStartBindingSession:
    """Tests for POST /me/im-bindings/{channel_id}/start-session endpoint."""

    @pytest.mark.asyncio
    async def test_start_binding_session_success(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test starting a binding session successfully."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.set = AsyncMock(return_value=True)

            response = im_bindings_client.post(
                f"/api/users/me/im-bindings/{sample_messager_channel.id}/start-session"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "session started" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_start_binding_session_failure(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test starting a binding session when cache fails."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.set = AsyncMock(return_value=False)

            response = im_bindings_client.post(
                f"/api/users/me/im-bindings/{sample_messager_channel.id}/start-session"
            )

            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()


@pytest.mark.api
class TestCancelBindingSession:
    """Tests for POST /me/im-bindings/{channel_id}/cancel-session endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_binding_session_success(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test cancelling a binding session successfully."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.delete = AsyncMock(return_value=True)

            response = im_bindings_client.post(
                f"/api/users/me/im-bindings/{sample_messager_channel.id}/cancel-session"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "cancelled" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_cancel_binding_session_failure(
        self,
        im_bindings_client: TestClient,
        sample_messager_channel: Kind,
    ):
        """Test cancelling a binding session when cache raises exception."""
        with patch("app.services.channels.binding_service.cache_manager") as mock_cache:
            mock_cache.delete = AsyncMock(
                side_effect=Exception("Redis connection failed")
            )

            response = im_bindings_client.post(
                f"/api/users/me/im-bindings/{sample_messager_channel.id}/cancel-session"
            )

            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
