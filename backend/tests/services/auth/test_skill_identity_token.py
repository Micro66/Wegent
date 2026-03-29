# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for skill identity token authentication."""

from app.services.auth import create_skill_identity_token, verify_skill_identity_token


class TestCreateSkillIdentityToken:
    """Tests for create_skill_identity_token function."""

    def test_create_and_verify_skill_identity_token(self):
        """A created token should round-trip into token info."""
        token = create_skill_identity_token(
            user_id=7,
            user_name="alice",
            runtime_type="executor",
            runtime_name="executor-1",
        )

        info = verify_skill_identity_token(token)

        assert info is not None
        assert info.user_id == 7
        assert info.user_name == "alice"
        assert info.runtime_type == "executor"
        assert info.runtime_name == "executor-1"


class TestVerifySkillIdentityToken:
    """Tests for verify_skill_identity_token function."""

    def test_verify_invalid_skill_identity_token(self):
        """Invalid token strings should be rejected."""
        assert verify_skill_identity_token("invalid-token") is None
