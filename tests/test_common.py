"""Tests for the shared layer and graceful degradation (no network, no creds)."""

import os

from overseas_social_mcp.common import RateLimiter, err_result, make_item, ok_result
from overseas_social_mcp.config import Settings


def test_make_item_schema():
    item = make_item(id="1", author="a", content="hi", like_count=5, url="http://x/1")
    assert set(item) == {
        "id", "author", "author_id", "content", "like_count",
        "comment_count", "publish_time", "url", "extra", "raw",
    }
    assert item["extra"] == {}


def test_ok_and_err_result():
    res = ok_result("x", "X / Twitter", [make_item(id="1", author="a", content="hi")])
    assert res["ok"] is True and res["count"] == 1
    e = err_result("backend_unavailable", ["missing dep"])
    assert e["ok"] is False and e["error"] == "backend_unavailable"


def test_clamp_count():
    s = Settings()
    val, warns = s.clamp_count(None)
    assert val == s.default_max_count and warns == []
    val, warns = s.clamp_count(10_000)
    assert val == s.max_count_hard_limit and warns


def test_rate_limiter():
    rl = RateLimiter(max_calls=1, window_seconds=100)
    assert rl.acquire()[0] is True
    allowed, retry = rl.acquire()
    assert allowed is False and retry > 0


def test_backends_degrade_without_deps(monkeypatch):
    # With no creds/deps configured, calling a backend must raise
    # BackendUnavailable (caught by the server into a structured error), never
    # a bare crash. We assert the reddit backend specifically because it checks
    # credentials before importing praw.
    from overseas_social_mcp.backends import reddit_backend
    from overseas_social_mcp.common import BackendUnavailable

    s = Settings()
    s.reddit_client_id = ""
    s.reddit_client_secret = ""
    try:
        reddit_backend.search(s, "test", 5)
        assert False, "expected BackendUnavailable"
    except BackendUnavailable as exc:
        assert "credentials" in str(exc).lower()
