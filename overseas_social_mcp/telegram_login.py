"""One-time Telegram (Telethon) login for the overseas-social MCP server.

Run it yourself in a terminal. It prompts for secrets, so never have an agent
type them for you:

    cd ~/mcp-servers/overseas-social-mcp && python3 -m overseas_social_mcp.telegram_login

1. Asks for api_id / api_hash (create an app at https://my.telegram.org ->
   "API development tools") unless the env file already has them.
2. Saves them to the env file (~/.config/overseas-social-mcp/.env, chmod 600),
   which every server process loads at startup.
3. Logs in with phone number + login code (+ 2FA password) and writes the
   session file (chmod 600).

Options:
    --check   report status without prompting (safe for agents to run)
    --reset   forget the saved api_id / api_hash and session, then log in again
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import sys

from .backends.telegram_backend import LOGIN_COMMAND, session_file, session_lock
from .config import env_file_path, get_settings

_TG_KEYS = ("OSMCP_TG_API_ID", "OSMCP_TG_API_HASH", "OSMCP_TG_SESSION")


def _update_env_file(path: str, values: dict[str, str | None]) -> None:
    """Set (or, for None, remove) keys in the env file, keeping other lines; chmod 600."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = []
    pending = dict(values)
    out: list[str] = []
    for line in lines:
        key = line.partition("=")[0].strip().removeprefix("export ").strip()
        if key in pending:
            value = pending.pop(key)
            if value is not None:
                out.append(f"{key}={value}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in pending.items() if v is not None)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n" if out else "")
    os.replace(tmp, path)


def _prompt(label: str, pattern: str, *, hidden: bool) -> str:
    while True:
        value = (getpass.getpass(label) if hidden else input(label)).strip()
        if re.fullmatch(pattern, value):
            return value
        print("  That doesn't look right, try again (Ctrl+C to quit).")


def _describe(me) -> str:
    name = " ".join(p for p in (me.first_name, me.last_name) if p) or "(no name)"
    return f"{name} (@{me.username})" if me.username else name


async def _whoami(path: str, api_id: str, api_hash: str) -> str | None:
    from telethon import TelegramClient

    client = TelegramClient(path, int(api_id), api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            return None
        return _describe(await client.get_me())
    finally:
        await client.disconnect()


async def _login(path: str, api_id: str, api_hash: str) -> str:
    from telethon import TelegramClient

    client = TelegramClient(path, int(api_id), api_hash)
    try:
        await client.start(
            phone=lambda: input("Phone number (international format, e.g. +8613800000000): ").strip(),
            code_callback=lambda: input("Login code (sent to your Telegram app): ").strip(),
            password=lambda: getpass.getpass("2FA password (input hidden): "),
        )
        return _describe(await client.get_me())
    finally:
        await client.disconnect()


def check() -> int:
    settings = get_settings()
    path = session_file(settings)
    creds = bool(settings.telegram_api_id and settings.telegram_api_hash)
    env_path = env_file_path()
    print(f"env file:     {env_path} ({'found' if os.path.exists(env_path) else 'missing'})")
    print(f"credentials:  {'set' if creds else 'missing'}")
    print(f"session file: {path} ({'found' if os.path.exists(path) else 'missing'})")
    if not (creds and os.path.exists(path)):
        print(f"status:       NOT READY - the user must run in their own terminal: {LOGIN_COMMAND}")
        return 1
    with session_lock(path):
        who = asyncio.run(_whoami(path, settings.telegram_api_id, settings.telegram_api_hash))
    if who is None:
        print(f"status:       NOT AUTHORIZED - session was logged out; the user must rerun: {LOGIN_COMMAND}")
        return 1
    print(f"status:       READY - logged in as {who}")
    return 0


def login(reset: bool) -> int:
    env_path = env_file_path()
    if reset:
        _update_env_file(env_path, {k: None for k in _TG_KEYS})
        for key in _TG_KEYS:
            os.environ.pop(key, None)
    settings = get_settings()
    path = session_file(settings)
    if reset and os.path.exists(path):
        os.remove(path)
    api_id, api_hash = settings.telegram_api_id, settings.telegram_api_hash
    if not (api_id and api_hash):
        print("Create an app at https://my.telegram.org -> API development tools, then enter its values.")
        api_id = _prompt("api_id: ", r"\d{3,12}", hidden=False)
        api_hash = _prompt("api_hash (input hidden): ", r"[0-9a-fA-F]{32}", hidden=True)
    _update_env_file(env_path, {"OSMCP_TG_API_ID": api_id, "OSMCP_TG_API_HASH": api_hash, "OSMCP_TG_SESSION": path})
    print(f"Saved api_id / api_hash to {env_path} (chmod 600).")
    with session_lock(path):
        who = asyncio.run(_login(path, api_id, api_hash))
    os.chmod(path, 0o600)
    print(f"Logged in as {who}. Session file: {path}")
    print("New agent conversations can now use the telegram_channel_messages tool.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m overseas_social_mcp.telegram_login",
        description="One-time Telegram login for the overseas-social MCP server.",
    )
    parser.add_argument("--check", action="store_true", help="report status without prompting")
    parser.add_argument("--reset", action="store_true", help="forget saved api_id/api_hash and session, then log in again")
    args = parser.parse_args(argv)
    try:
        return check() if args.check else login(reset=args.reset)
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as exc:  # noqa: BLE001 - one readable line instead of a traceback
        if type(exc).__name__ == "ApiIdInvalidError":
            print("Telegram rejected the api_id / api_hash. Rerun with --reset and enter them again.")
        else:
            print(f"Failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
