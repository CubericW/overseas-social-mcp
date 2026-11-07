"""X / Twitter backend via twscrape (https://github.com/vladkens/twscrape).

twscrape is an async library with multi-account rotation. Accounts must be
added beforehand via its CLI, e.g. from a logged-in browser's cookies:

    twscrape --db ~/.config/overseas-social-mcp/x_accounts.db add_cookie my_account

Set OSMCP_X_ACCOUNTS_DB to use another sqlite db path. Without a usable account
twscrape only logs a warning and yields nothing, so calls check for one and
raise BackendUnavailable rather than report "0 tweets found".
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import sqlite3
from typing import Any
from urllib.parse import quote

from ..common import BackendUnavailable, make_item
from ..config import Settings


def add_account_command(settings: Settings) -> str:
    return f"twscrape --db {shlex.quote(settings.x_accounts_db)} add_cookie my_account"


def account_status(settings: Settings) -> dict[str, Any]:
    """Count accounts without creating the db (twscrape creates it on first use)."""
    status: dict[str, Any] = {"total": 0, "active": 0, "errors": []}
    if not os.path.exists(settings.x_accounts_db):
        return status
    try:
        uri = f"file:{quote(settings.x_accounts_db)}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as conn:
            rows = conn.execute("SELECT active, error_msg FROM accounts").fetchall()
    except sqlite3.Error as exc:
        status["errors"].append(f"{type(exc).__name__}: {exc}")
        return status
    status["total"] = len(rows)
    status["active"] = sum(1 for active, _ in rows if active)
    status["errors"] = sorted({msg for active, msg in rows if msg and not active})
    return status


def _require_active_account(settings: Settings) -> None:
    status = account_status(settings)
    if status["active"]:
        return
    state = f"{status['total']} account(s), none active" if status["total"] else "no accounts"
    errors = f" Errors: {'; '.join(status['errors'])}." if status["errors"] else ""
    raise BackendUnavailable(
        f"X accounts db {settings.x_accounts_db} has {state}.{errors} Ask the user to "
        f"add a logged-in account in their own terminal: {add_account_command(settings)}"
    )


def _load_api(settings: Settings):
    try:
        from twscrape import API  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise BackendUnavailable(
            "The 'twscrape' package is not installed. Install it with "
            "`pip install --user twscrape`, then add & login X accounts via its "
            "CLI. See https://github.com/vladkens/twscrape ."
        ) from exc
    _require_active_account(settings)
    return API(settings.x_accounts_db)


async def _search_async(settings: Settings, query: str, limit: int) -> list[dict[str, Any]]:
    api = _load_api(settings)
    items: list[dict[str, Any]] = []
    async for tweet in api.search(query, limit=limit):
        items.append(_tweet_to_item(tweet))
        if len(items) >= limit:
            break
    if not items:  # twscrape may have deactivated the account during this call
        _require_active_account(settings)
    return items


async def _user_tweets_async(settings: Settings, username: str, limit: int) -> list[dict[str, Any]]:
    api = _load_api(settings)
    user = await api.user_by_login(username)
    if user is None:
        _require_active_account(settings)
        return []
    items: list[dict[str, Any]] = []
    async for tweet in api.user_tweets(user.id, limit=limit):
        items.append(_tweet_to_item(tweet))
        if len(items) >= limit:
            break
    if not items:
        _require_active_account(settings)
    return items


def _tweet_to_item(tweet: Any) -> dict[str, Any]:
    user = getattr(tweet, "user", None)
    return make_item(
        id=str(getattr(tweet, "id", "") or ""),
        author=getattr(user, "username", None),
        author_id=str(getattr(user, "id", "") or "") or None,
        content=getattr(tweet, "rawContent", None) or getattr(tweet, "content", None),
        like_count=getattr(tweet, "likeCount", None),
        comment_count=getattr(tweet, "replyCount", None),
        publish_time=str(getattr(tweet, "date", "") or "") or None,
        url=getattr(tweet, "url", None),
        extra={
            "retweet_count": getattr(tweet, "retweetCount", None),
            "view_count": getattr(tweet, "viewCount", None),
            "lang": getattr(tweet, "lang", None),
        },
    )


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop (rare for stdio MCP); use a fresh loop in a thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def search(settings: Settings, query: str, limit: int) -> list[dict[str, Any]]:
    return _run(_search_async(settings, query, limit))


def user_posts(settings: Settings, username: str, limit: int) -> list[dict[str, Any]]:
    return _run(_user_tweets_async(settings, username.lstrip("@"), limit))
