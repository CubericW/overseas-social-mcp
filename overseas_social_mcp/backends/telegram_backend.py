"""Telegram backend via Telethon (official MTProto API).

Get api_id / api_hash from https://my.telegram.org, then log in once in your
own terminal (it prompts for api_id / api_hash, phone, login code and 2FA):

    python3 -m overseas_social_mcp.telegram_login

That stores OSMCP_TG_API_ID / OSMCP_TG_API_HASH / OSMCP_TG_SESSION in the env
file (~/.config/overseas-social-mcp/.env) and creates the session file, which
the server then reuses headlessly.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shlex
import time
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

from ..common import BackendUnavailable, make_item
from ..config import Settings

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGIN_COMMAND = f"cd {shlex.quote(_PROJECT_ROOT)} && python3 -m overseas_social_mcp.telegram_login"

_TME_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/(?:s/)?", re.IGNORECASE)


def normalize_channel(channel: str) -> str | int:
    """Map '@name', 't.me/name', 't.me/s/name/123', 't.me/c/<id>/5' or '-100…' to a get_entity() ref."""
    ref = (channel or "").strip()
    parts = _TME_PREFIX.sub("", ref).split("?", 1)[0].strip("/").split("/")
    if parts[0].startswith("+") or parts[0] == "joinchat":
        return ref  # invite link: Telethon resolves it only if the account is a member
    if parts[0] == "c" and len(parts) > 1 and parts[1].isdigit():
        return int("-100" + parts[1])
    name = parts[0].lstrip("@")
    if not name:
        raise ValueError("channel is empty")
    if re.fullmatch(r"-?\d+", name):
        return int(name)
    return name


def session_file(settings: Settings) -> str:
    """Session path exactly as Telethon stores it (it appends '.session')."""
    path = os.path.expanduser(settings.telegram_session)
    return path if path.endswith(".session") else path + ".session"


@contextlib.contextmanager
def session_lock(path: str, timeout: float = 90.0) -> Iterator[None]:
    """Serialise session use across processes (each agent session runs its own server).

    Telethon keeps the session in SQLite; concurrent writers fail with
    'database is locked'.
    """
    if fcntl is None:  # pragma: no cover
        yield
        return
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    with open(path + ".lock", "a") as fh:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Telegram session is busy in another agent session; retry shortly.") from None
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ensure_deps(settings: Settings):
    if not (settings.telegram_api_id and settings.telegram_api_hash):
        raise BackendUnavailable(
            "Telegram credentials are missing (OSMCP_TG_API_ID / OSMCP_TG_API_HASH). "
            f"Ask the user to run the one-time login in their own terminal: {LOGIN_COMMAND}"
        )
    if not os.path.exists(session_file(settings)):
        raise BackendUnavailable(
            f"Telegram session file {session_file(settings)} does not exist. "
            f"Ask the user to run the one-time login in their own terminal: {LOGIN_COMMAND}"
        )
    try:
        from telethon import TelegramClient  # type: ignore  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise BackendUnavailable(
            "The 'telethon' package is not installed. Install it with "
            "`pip install --user telethon`."
        ) from exc


def _message_url(entity: Any, msg_id: Any) -> str | None:
    username = getattr(entity, "username", None) or next(
        (u.username for u in (getattr(entity, "usernames", None) or []) if getattr(u, "active", False)), None
    )
    if username:
        return f"https://t.me/{username}/{msg_id}"
    if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
        return f"https://t.me/c/{entity.id}/{msg_id}"  # private channel: opens for members only
    return None


async def _channel_messages_async(settings: Settings, channel: str, limit: int, query: str | None) -> list[dict[str, Any]]:
    from telethon import TelegramClient  # type: ignore
    from telethon.utils import get_display_name  # type: ignore

    client = TelegramClient(
        session_file(settings),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
    )
    items: list[dict[str, Any]] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise BackendUnavailable(
                "Telegram session is not authorized (logged out or revoked). "
                f"Ask the user to rerun the login in their own terminal: {LOGIN_COMMAND}"
            )
        # get_input_entity checks the session cache first; get_entity(str) would send
        # ResolveUsernameRequest on every call, which Telegram flood-limits hard.
        peer = await client.get_input_entity(normalize_channel(channel))
        kwargs: dict[str, Any] = {"limit": limit}
        if query:
            kwargs["search"] = query
        async for msg in client.iter_messages(peer, **kwargs):
            text = getattr(msg, "message", None)
            if text is None and query:
                continue
            chat = getattr(msg, "chat", None)
            sender = getattr(msg, "sender", None)
            items.append(
                make_item(
                    id=str(getattr(msg, "id", "") or ""),
                    author=getattr(msg, "post_author", None)
                    or (get_display_name(sender) if sender else "")
                    or (get_display_name(chat) if chat else "")
                    or None,
                    author_id=str(msg.sender_id) if getattr(msg, "sender_id", None) else None,
                    content=text,
                    like_count=None,
                    comment_count=getattr(getattr(msg, "replies", None), "replies", None),
                    publish_time=str(getattr(msg, "date", "") or "") or None,
                    url=_message_url(chat, getattr(msg, "id", "")),
                    extra={
                        "views": getattr(msg, "views", None),
                        "forwards": getattr(msg, "forwards", None),
                    },
                )
            )
            if len(items) >= limit:
                break
    finally:
        await client.disconnect()
    return items


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def channel_messages(settings: Settings, channel: str, limit: int, query: str | None = None) -> list[dict[str, Any]]:
    _ensure_deps(settings)
    with session_lock(session_file(settings), timeout=settings.request_timeout_seconds):
        return _run(_channel_messages_async(settings, channel, limit, query))
