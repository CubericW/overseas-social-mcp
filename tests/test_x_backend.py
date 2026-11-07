"""X backend account handling (no network, no creds)."""

import asyncio
import os
import sqlite3
from types import SimpleNamespace

import pytest

from overseas_social_mcp.backends import x_backend
from overseas_social_mcp.common import BackendUnavailable
from overseas_social_mcp.config import DEFAULT_X_ACCOUNTS_DB, Settings

pytest.importorskip("twscrape")


@pytest.fixture
def settings(tmp_path):
    return Settings(x_accounts_db=str(tmp_path / "x accounts.db"))


def _add_account(settings, username="acct", cookies="auth_token=a; ct0=b"):
    from twscrape import AccountsPool

    asyncio.run(AccountsPool(settings.x_accounts_db).add_account_cookies(username, cookies))


def _deactivate(settings, error_msg=None):
    with sqlite3.connect(settings.x_accounts_db) as conn:
        conn.execute("UPDATE accounts SET active = 0, error_msg = ?", (error_msg,))


class FakeApi:
    def __init__(self, tweets=(), on_search=None):
        self.tweets = tweets
        self.on_search = on_search

    async def search(self, query, limit):
        if self.on_search:
            self.on_search()
        for tweet in self.tweets:
            yield tweet

    async def user_by_login(self, username):
        if self.on_search:
            self.on_search()
        return None


def test_default_db_does_not_depend_on_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("OSMCP_X_ACCOUNTS_DB", raising=False)
    monkeypatch.chdir(tmp_path)
    assert Settings().x_accounts_db == DEFAULT_X_ACCOUNTS_DB
    assert os.path.isabs(DEFAULT_X_ACCOUNTS_DB)


def test_env_db_path_expands_user(monkeypatch):
    monkeypatch.setenv("OSMCP_X_ACCOUNTS_DB", "~/custom.db")
    assert Settings().x_accounts_db == os.path.expanduser("~/custom.db")


def test_status_of_missing_db_does_not_create_it(settings):
    assert x_backend.account_status(settings) == {"total": 0, "active": 0, "errors": []}
    assert not os.path.exists(settings.x_accounts_db)


def test_status_reads_twscrape_schema(settings):
    _add_account(settings, "with_cookies")
    _add_account(settings, "inactive")
    from twscrape import AccountsPool

    asyncio.run(AccountsPool(settings.x_accounts_db).set_active("inactive", False))
    status = x_backend.account_status(settings)
    assert (status["total"], status["active"]) == (2, 1)


def test_status_survives_db_without_accounts_table(settings):
    sqlite3.connect(settings.x_accounts_db).close()
    status = x_backend.account_status(settings)
    assert (status["total"], status["active"]) == (0, 0)
    assert "no such table" in status["errors"][0]


def test_search_without_accounts_is_unavailable_and_creates_no_db(monkeypatch, settings, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(BackendUnavailable, match="no accounts.*add_cookie"):
        x_backend.search(settings, "python", 1)
    assert os.listdir(tmp_path) == []


def test_inactive_account_reports_its_error(settings):
    _add_account(settings)
    _deactivate(settings, "HTTP 403")
    with pytest.raises(BackendUnavailable, match="1 account.*none active.*HTTP 403"):
        x_backend.search(settings, "python", 1)


def test_active_account_with_no_matches_is_a_real_empty_result(monkeypatch, settings):
    _add_account(settings)
    monkeypatch.setattr(x_backend, "_load_api", lambda s: FakeApi())
    assert x_backend.search(settings, "nothing matches", 5) == []


def test_account_deactivated_during_search_is_unavailable(monkeypatch, settings):
    _add_account(settings)
    api = FakeApi(on_search=lambda: _deactivate(settings, "Session expired"))
    monkeypatch.setattr(x_backend, "_load_api", lambda s: api)
    with pytest.raises(BackendUnavailable, match="Session expired"):
        x_backend.search(settings, "python", 5)


def test_account_deactivated_during_user_lookup_is_unavailable(monkeypatch, settings):
    _add_account(settings)
    api = FakeApi(on_search=lambda: _deactivate(settings))
    monkeypatch.setattr(x_backend, "_load_api", lambda s: api)
    with pytest.raises(BackendUnavailable, match="none active"):
        x_backend.user_posts(settings, "@someone", 5)


def test_user_not_found_with_active_account_is_empty(monkeypatch, settings):
    _add_account(settings)
    monkeypatch.setattr(x_backend, "_load_api", lambda s: FakeApi())
    assert x_backend.user_posts(settings, "@nobody", 5) == []


def test_search_normalises_tweets(monkeypatch, settings):
    _add_account(settings)
    tweet = SimpleNamespace(
        id=1, user=SimpleNamespace(username="a", id=2), rawContent="hi", likeCount=3,
        replyCount=4, date="2026-11-03", url="https://x.com/a/status/1",
        retweetCount=5, viewCount=6, lang="en",
    )
    monkeypatch.setattr(x_backend, "_load_api", lambda s: FakeApi(tweets=[tweet]))
    [item] = x_backend.search(settings, "python", 5)
    assert (item["id"], item["author"], item["content"], item["like_count"]) == ("1", "a", "hi", 3)
    assert item["extra"]["view_count"] == 6
