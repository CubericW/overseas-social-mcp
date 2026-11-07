"""Overseas Social MCP server entry point.

Run with:  python -m overseas_social_mcp.server

Tools:
    x_search / x_user_posts
    reddit_search / reddit_subreddit_hot / reddit_post_comments
    telegram_channel_messages
    linkedin_profile / linkedin_company
    list_platforms / backend_status

Every tool degrades gracefully: a missing dependency or credential yields a
structured `{ok: false, error: "backend_unavailable", details: [...]}` payload
with actionable setup instructions, never a crash.

SAFETY: personal / low-frequency / research use only. Prefer official APIs
(Reddit, Telegram). Respect each platform's ToS.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .backends import linkedin_backend, reddit_backend, telegram_backend, x_backend
from .common import BackendUnavailable, RateLimiter, err_result, ok_result
from .config import PLATFORM_NAMES, PLATFORMS, get_settings

mcp = FastMCP("overseas-social-mcp")

_settings = get_settings()
_rate_limiter = RateLimiter(_settings.rate_limit_calls, _settings.rate_limit_window_seconds)


def _reload_if_telegram_unconfigured() -> None:
    """The user may run the Telegram login after this server started; pick it up."""
    global _settings
    if not (_settings.telegram_api_id and _settings.telegram_api_hash):
        _settings = get_settings(refresh=True)


def _guard() -> dict[str, Any] | None:
    allowed, retry_after = _rate_limiter.acquire()
    if not allowed:
        return err_result(
            "rate_limited",
            [
                f"Local rate limit reached ({_settings.rate_limit_calls} calls / "
                f"{_settings.rate_limit_window_seconds}s). Retry in {retry_after:.0f}s. "
                "This guard reduces ban / API-throttle risk."
            ],
        )
    return None


def _call(platform: str, fn, **kwargs) -> dict[str, Any]:
    guard = _guard()
    if guard:
        return guard
    try:
        items = fn(**kwargs)
    except BackendUnavailable as exc:
        return err_result("backend_unavailable", [str(exc)])
    except Exception as exc:  # noqa: BLE001 - surface as structured error
        return err_result("backend_error", [f"{type(exc).__name__}: {exc}"])
    return ok_result(platform, PLATFORM_NAMES[platform], items)


# ---- X / Twitter -----------------------------------------------------------


@mcp.tool()
def x_search(query: str, max_count: int | None = None) -> dict[str, Any]:
    """Search recent public tweets on X/Twitter matching a query.

    Args:
        query: X search query (supports X search operators, e.g. `from:user`,
            `lang:en`, `since:2026-01-01`).
        max_count: max tweets to return (default from config, hard-capped).

    Returns normalised items: {id, author, content, like_count, comment_count,
    publish_time, url, extra:{retweet_count, view_count, lang}}.
    Requires twscrape installed + X accounts added & logged in.
    """
    count, warnings = _settings.clamp_count(max_count)
    res = _call("x", x_backend.search, settings=_settings, query=query, limit=count)
    if res.get("ok"):
        res["query"] = query
        res["warnings"] = warnings + res.get("warnings", [])
    return res


@mcp.tool()
def x_user_posts(username: str, max_count: int | None = None) -> dict[str, Any]:
    """Fetch recent public tweets from a specific X/Twitter user.

    Args:
        username: handle with or without leading @.
        max_count: max tweets (default from config, hard-capped).
    """
    count, warnings = _settings.clamp_count(max_count)
    res = _call("x", x_backend.user_posts, settings=_settings, username=username, limit=count)
    if res.get("ok"):
        res["username"] = username
        res["warnings"] = warnings + res.get("warnings", [])
    return res


# ---- Reddit ----------------------------------------------------------------


@mcp.tool()
def reddit_search(query: str, subreddit: str | None = None, max_count: int | None = None) -> dict[str, Any]:
    """Search Reddit posts (optionally within one subreddit) via the official API.

    Args:
        query: search query.
        subreddit: optional subreddit name (without r/); searches r/all if omitted.
        max_count: max posts (default from config, hard-capped).
    """
    count, warnings = _settings.clamp_count(max_count)
    res = _call("reddit", reddit_backend.search, settings=_settings, query=query, limit=count, subreddit=subreddit)
    if res.get("ok"):
        res["query"] = query
        res["warnings"] = warnings + res.get("warnings", [])
    return res


@mcp.tool()
def reddit_subreddit_hot(subreddit: str, max_count: int | None = None) -> dict[str, Any]:
    """Fetch hot posts from a subreddit via the official API.

    Args:
        subreddit: subreddit name (without r/).
        max_count: max posts (default from config, hard-capped).
    """
    count, warnings = _settings.clamp_count(max_count)
    res = _call("reddit", reddit_backend.subreddit_hot, settings=_settings, subreddit=subreddit, limit=count)
    if res.get("ok"):
        res["subreddit"] = subreddit
        res["warnings"] = warnings + res.get("warnings", [])
    return res


@mcp.tool()
def reddit_post_comments(post_id: str, max_count: int | None = None) -> dict[str, Any]:
    """Fetch top-level comments of a Reddit post by its id.

    Args:
        post_id: Reddit submission id (the base36 id, not the full URL).
        max_count: max comments (default from config, hard-capped).
    """
    count, warnings = _settings.clamp_count(max_count)
    res = _call("reddit", reddit_backend.post_comments, settings=_settings, post_id=post_id, limit=count)
    if res.get("ok"):
        res["post_id"] = post_id
        res["warnings"] = warnings + res.get("warnings", [])
    return res


# ---- Telegram --------------------------------------------------------------


@mcp.tool()
def telegram_channel_messages(
    channel: str, query: str | None = None, max_count: int | None = None
) -> dict[str, Any]:
    """Fetch recent messages from a public Telegram channel or group (optionally filtered).

    Args:
        channel: channel/group username (with or without @), a t.me link
            (t.me/name, t.me/s/name, t.me/name/123), or a numeric -100… id.
        query: optional keyword to filter messages server-side.
        max_count: max messages (default from config, hard-capped).

    Items are newest first; publish_time is UTC. Requires telethon +
    api_id/api_hash + an authorized session (one-time interactive login:
    `python3 -m overseas_social_mcp.telegram_login`, run by the user).
    """
    _reload_if_telegram_unconfigured()
    count, warnings = _settings.clamp_count(max_count)
    res = _call(
        "telegram",
        telegram_backend.channel_messages,
        settings=_settings,
        channel=channel,
        limit=count,
        query=query,
    )
    if res.get("ok"):
        res["channel"] = channel
        res["warnings"] = warnings + res.get("warnings", [])
    return res


# ---- LinkedIn --------------------------------------------------------------


@mcp.tool()
def linkedin_profile(profile_url: str) -> dict[str, Any]:
    """Fetch a single LinkedIn profile (name, headline, experience, education).

    HIGH RISK: violates LinkedIn ToS and may restrict your account. Disabled by
    default; enable via OSMCP_LINKEDIN_ENABLED=true with a throwaway account.

    Args:
        profile_url: full https://www.linkedin.com/in/... URL.
    """
    return _call("linkedin", linkedin_backend.get_profile, settings=_settings, profile_url=profile_url)


@mcp.tool()
def linkedin_company(company_url: str) -> dict[str, Any]:
    """Fetch a single LinkedIn company page (industry, size, HQ, about).

    HIGH RISK: see linkedin_profile. Disabled by default.

    Args:
        company_url: full https://www.linkedin.com/company/... URL.
    """
    return _call("linkedin", linkedin_backend.get_company, settings=_settings, company_url=company_url)


# ---- meta ------------------------------------------------------------------


@mcp.tool()
def list_platforms() -> dict[str, Any]:
    """List supported platforms and their tools."""
    return {
        "ok": True,
        "platforms": [
            {"code": "x", "name": PLATFORM_NAMES["x"], "tools": ["x_search", "x_user_posts"], "api": "twscrape (unofficial)"},
            {"code": "reddit", "name": PLATFORM_NAMES["reddit"], "tools": ["reddit_search", "reddit_subreddit_hot", "reddit_post_comments"], "api": "PRAW (official)"},
            {"code": "telegram", "name": PLATFORM_NAMES["telegram"], "tools": ["telegram_channel_messages"], "api": "Telethon (official MTProto)"},
            {"code": "linkedin", "name": PLATFORM_NAMES["linkedin"], "tools": ["linkedin_profile", "linkedin_company"], "api": "linkedin_scraper (unofficial, high-risk)"},
        ],
        "notes": [
            "Prefer official APIs (Reddit, Telegram).",
            "Personal, low-frequency, research use only. Respect platform ToS.",
        ],
    }


@mcp.tool()
def backend_status() -> dict[str, Any]:
    """Report which backends are configured & importable (without making calls)."""
    _reload_if_telegram_unconfigured()
    status: dict[str, Any] = {}

    # X
    x_dep = _module_available("twscrape")
    x_accounts = x_backend.account_status(_settings)
    status["x"] = {
        "dependency_installed": x_dep,
        "accounts_db": _settings.x_accounts_db,
        "accounts_total": x_accounts["total"],
        "accounts_active": x_accounts["active"],
        "ready": x_dep and x_accounts["active"] > 0,
    }
    if x_accounts["errors"]:
        status["x"]["account_errors"] = x_accounts["errors"]
    if not status["x"]["ready"]:
        status["x"]["setup"] = f"User runs once in their own terminal: {x_backend.add_account_command(_settings)}"
    # Reddit
    reddit_dep = _module_available("praw")
    reddit_creds = bool(_settings.reddit_client_id and _settings.reddit_client_secret)
    status["reddit"] = {
        "dependency_installed": reddit_dep,
        "credentials_set": reddit_creds,
        "ready": reddit_dep and reddit_creds,
    }
    # Telegram (session authorization is only verified on the first real call)
    tg_dep = _module_available("telethon")
    tg_creds = bool(_settings.telegram_api_id and _settings.telegram_api_hash)
    tg_session = telegram_backend.session_file(_settings)
    tg_session_exists = os.path.exists(tg_session)
    status["telegram"] = {
        "dependency_installed": tg_dep,
        "credentials_set": tg_creds,
        "session_file": tg_session,
        "session_exists": tg_session_exists,
        "ready": tg_dep and tg_creds and tg_session_exists,
    }
    if not status["telegram"]["ready"]:
        status["telegram"]["setup"] = f"User runs once in their own terminal: {telegram_backend.LOGIN_COMMAND}"
    # LinkedIn
    li_dep = _module_available("linkedin_scraper") and _module_available("selenium")
    li_creds = bool(_settings.linkedin_email and _settings.linkedin_password)
    status["linkedin"] = {
        "enabled": _settings.linkedin_enabled,
        "dependency_installed": li_dep,
        "credentials_set": li_creds,
        "ready": _settings.linkedin_enabled and li_dep and li_creds,
        "note": "High-risk; disabled by default.",
    }
    return {"ok": True, "backends": status}


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
