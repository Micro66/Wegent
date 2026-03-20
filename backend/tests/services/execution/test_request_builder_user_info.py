# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for git account matching in TaskRequestBuilder._build_user_info."""

from types import SimpleNamespace

from app.services.execution.request_builder import TaskRequestBuilder


class TestBuildUserInfoGitDomainMatch:
    """Tests for git domain matching behavior in _build_user_info."""

    def test_matches_domain_even_when_saved_with_protocol(self):
        builder = TaskRequestBuilder.__new__(TaskRequestBuilder)
        user = SimpleNamespace(
            id=1,
            user_name="tester",
            git_info=[
                {
                    "git_domain": "github.com",
                    "git_token": "github-token",
                    "git_login": "gh-user",
                },
                {
                    "git_domain": "http://gerrit.client.weibo.cn",
                    "git_token": "gerrit-token",
                    "git_login": "gerrit-user",
                },
            ],
        )

        user_info = builder._build_user_info(user, "gerrit.client.weibo.cn")

        assert user_info["git_domain"] == "http://gerrit.client.weibo.cn"
        assert user_info["git_token"] == "gerrit-token"
        assert user_info["git_login"] == "gerrit-user"

    def test_matches_domain_even_when_request_contains_protocol(self):
        builder = TaskRequestBuilder.__new__(TaskRequestBuilder)
        user = SimpleNamespace(
            id=1,
            user_name="tester",
            git_info=[
                {
                    "git_domain": "gerrit.client.weibo.cn",
                    "git_token": "gerrit-token",
                    "git_login": "gerrit-user",
                },
            ],
        )

        user_info = builder._build_user_info(user, "http://gerrit.client.weibo.cn")

        assert user_info["git_domain"] == "gerrit.client.weibo.cn"
        assert user_info["git_token"] == "gerrit-token"
        assert user_info["git_login"] == "gerrit-user"

    def test_does_not_fallback_to_first_account_when_domain_specified(self):
        builder = TaskRequestBuilder.__new__(TaskRequestBuilder)
        user = SimpleNamespace(
            id=1,
            user_name="tester",
            git_info=[
                {
                    "git_domain": "github.com",
                    "git_token": "github-token",
                    "git_login": "gh-user",
                },
            ],
        )

        user_info = builder._build_user_info(user, "gerrit.client.weibo.cn")

        assert user_info["git_domain"] is None
        assert user_info["git_token"] is None
        assert user_info["git_login"] is None
