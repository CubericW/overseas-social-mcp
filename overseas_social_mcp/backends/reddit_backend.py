"""Reddit backend via PRAW (official Reddit API).

Create a script app at https://www.reddit.com/prefs/apps to obtain a
client id + secret, then set:
    OSMCP_REDDIT_CLIENT_ID, OSMCP_REDDIT_CLIENT_SECRET, OSMCP_REDDIT_USER_AGENT

Read-only ("application-only") auth is sufficient for public data.
"""

from __future__ import annotations

from typing import Any

from ..common import BackendUnavailable, make_item
from ..config import Settings


def _client(settings: Settings):
    if not (settings.reddit_client_id and settings.reddit_client_secret):
        raise BackendUnavailable(
            "Reddit credentials are missing. Create a 'script' app at "
            "https://www.reddit.com/prefs/apps and set OSMCP_REDDIT_CLIENT_ID / "
            "OSMCP_REDDIT_CLIENT_SECRET / OSMCP_REDDIT_USER_AGENT."
        )
    try:
        import praw  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise BackendUnavailable(
            "The 'praw' package is not installed. Install it with "
            "`pip install --user praw`."
        ) from exc
    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        check_for_async=False,
    )


def _submission_to_item(sub: Any) -> dict[str, Any]:
    return make_item(
        id=str(getattr(sub, "id", "") or ""),
        author=str(getattr(sub, "author", "") or "") or None,
        content=(getattr(sub, "title", "") or "") + (
            "\n\n" + sub.selftext if getattr(sub, "selftext", "") else ""
        ),
        like_count=getattr(sub, "score", None),
        comment_count=getattr(sub, "num_comments", None),
        publish_time=getattr(sub, "created_utc", None),
        url="https://www.reddit.com" + getattr(sub, "permalink", "") if getattr(sub, "permalink", "") else getattr(sub, "url", None),
        extra={
            "subreddit": str(getattr(sub, "subreddit", "") or ""),
            "upvote_ratio": getattr(sub, "upvote_ratio", None),
            "over_18": getattr(sub, "over_18", None),
        },
    )


def search(settings: Settings, query: str, limit: int, subreddit: str | None = None) -> list[dict[str, Any]]:
    reddit = _client(settings)
    target = reddit.subreddit(subreddit) if subreddit else reddit.subreddit("all")
    items: list[dict[str, Any]] = []
    for sub in target.search(query, limit=limit):
        items.append(_submission_to_item(sub))
    return items


def subreddit_hot(settings: Settings, subreddit: str, limit: int) -> list[dict[str, Any]]:
    reddit = _client(settings)
    items: list[dict[str, Any]] = []
    for sub in reddit.subreddit(subreddit).hot(limit=limit):
        items.append(_submission_to_item(sub))
    return items


def post_comments(settings: Settings, post_id: str, limit: int) -> list[dict[str, Any]]:
    reddit = _client(settings)
    submission = reddit.submission(id=post_id)
    submission.comments.replace_more(limit=0)
    items: list[dict[str, Any]] = []
    for comment in submission.comments.list()[:limit]:
        items.append(
            make_item(
                id=str(getattr(comment, "id", "") or ""),
                author=str(getattr(comment, "author", "") or "") or None,
                content=getattr(comment, "body", None),
                like_count=getattr(comment, "score", None),
                publish_time=getattr(comment, "created_utc", None),
                url=None,
            )
        )
    return items
