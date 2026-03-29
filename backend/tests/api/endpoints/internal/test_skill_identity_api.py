# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for internal skill identity verification API."""

from app.services.auth import create_skill_identity_token


def test_verify_skill_identity_returns_true_for_matching_user(test_client):
    """Matching token and user_name should verify successfully."""
    token = create_skill_identity_token(
        user_id=1,
        user_name="alice",
        runtime_type="executor",
        runtime_name="executor-1",
    )

    response = test_client.post(
        "/api/internal/skill-identity/verify",
        json={"token": token, "user_name": "alice"},
    )

    assert response.status_code == 200
    assert response.json() == {"matched": True}


def test_verify_skill_identity_does_not_leak_real_username_on_mismatch(test_client):
    """Mismatch responses should not leak the token owner identity."""
    token = create_skill_identity_token(
        user_id=1,
        user_name="alice",
        runtime_type="executor",
        runtime_name="executor-1",
    )

    response = test_client.post(
        "/api/internal/skill-identity/verify",
        json={"token": token, "user_name": "bob"},
    )

    assert response.status_code == 200
    assert response.json() == {"matched": False, "reason": "user_mismatch"}
    assert "alice" not in response.text
