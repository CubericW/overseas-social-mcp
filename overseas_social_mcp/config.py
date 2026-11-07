"""Configuration for the Overseas Social MCP server.

All settings come from environment variables so the server can be configured
entirely through the MCP client's `env` block. See .env.example.

Secrets can instead live in an env file (default
~/.config/overseas-social-mcp/.env, override with OSMCP_ENV_FILE). It is
loaded before settings are built; variables already set by the MCP client win.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

CONFIG_DIR = os.path.expanduser("~/.config/overseas-social-mcp")
DEFAULT_ENV_FILE = os.path.join(CONFIG_DIR, ".env")
DEFAULT_TG_SESSION = os.path.join(CONFIG_DIR, "telegram.session")
DEFAULT_X_ACCOUNTS_DB = os.path.join(CONFIG_DIR, "x_accounts.db")

PLATFORMS = ("x", "reddit", "telegram", "linkedin")

PLATFORM_NAMES = {
    "x": "X / Twitter",
    "reddit": "Reddit",
    "telegram": "Telegram",
    "linkedin": "LinkedIn",
}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def env_file_path() -> str:
    return os.path.expanduser(os.environ.get("OSMCP_ENV_FILE", DEFAULT_ENV_FILE))


def load_env_file(path: str | None = None) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing vars."""
    try:
        with open(path or env_file_path(), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


@dataclass
class Settings:
    # ---- global guardrails ------------------------------------------------
    default_max_count: int = field(default_factory=lambda: _get_int("OSMCP_DEFAULT_MAX", 20))
    max_count_hard_limit: int = field(default_factory=lambda: _get_int("OSMCP_MAX_HARD_LIMIT", 100))
    delay_min_seconds: float = field(default_factory=lambda: _get_float("OSMCP_DELAY_MIN", 1.0))
    delay_max_seconds: float = field(default_factory=lambda: _get_float("OSMCP_DELAY_MAX", 3.0))
    rate_limit_calls: int = field(default_factory=lambda: _get_int("OSMCP_RATE_CALLS", 20))
    rate_limit_window_seconds: int = field(default_factory=lambda: _get_int("OSMCP_RATE_WINDOW", 600))
    request_timeout_seconds: int = field(default_factory=lambda: _get_int("OSMCP_TIMEOUT", 60))

    # ---- X / Twitter (twscrape) ------------------------------------------
    # twscrape stores accounts in a local sqlite db created via its CLI.
    # Absolute by default: MCP servers start in whatever cwd the client picks.
    x_accounts_db: str = field(
        default_factory=lambda: os.path.expanduser(os.environ.get("OSMCP_X_ACCOUNTS_DB", "").strip() or DEFAULT_X_ACCOUNTS_DB)
    )
    x_enabled: bool = field(default_factory=lambda: _get_bool("OSMCP_X_ENABLED", True))

    # ---- Reddit (PRAW) ----------------------------------------------------
    reddit_client_id: str = field(default_factory=lambda: os.environ.get("OSMCP_REDDIT_CLIENT_ID", "").strip())
    reddit_client_secret: str = field(default_factory=lambda: os.environ.get("OSMCP_REDDIT_CLIENT_SECRET", "").strip())
    reddit_user_agent: str = field(
        default_factory=lambda: os.environ.get("OSMCP_REDDIT_USER_AGENT", "overseas-social-mcp/0.1 by research").strip()
    )

    # ---- Telegram (Telethon) ---------------------------------------------
    telegram_api_id: str = field(default_factory=lambda: os.environ.get("OSMCP_TG_API_ID", "").strip())
    telegram_api_hash: str = field(default_factory=lambda: os.environ.get("OSMCP_TG_API_HASH", "").strip())
    # Absolute by default: MCP servers start in whatever cwd the client picks.
    telegram_session: str = field(
        default_factory=lambda: os.path.expanduser(os.environ.get("OSMCP_TG_SESSION", "").strip() or DEFAULT_TG_SESSION)
    )

    # ---- LinkedIn (linkedin_scraper) -------------------------------------
    linkedin_email: str = field(default_factory=lambda: os.environ.get("OSMCP_LINKEDIN_EMAIL", "").strip())
    linkedin_password: str = field(default_factory=lambda: os.environ.get("OSMCP_LINKEDIN_PASSWORD", "").strip())
    linkedin_enabled: bool = field(default_factory=lambda: _get_bool("OSMCP_LINKEDIN_ENABLED", False))
    chromedriver_path: str = field(default_factory=lambda: os.environ.get("OSMCP_CHROMEDRIVER", "").strip())

    def clamp_count(self, requested: int | None) -> tuple[int, list[str]]:
        warnings: list[str] = []
        if requested is None:
            return self.default_max_count, warnings
        if requested > self.max_count_hard_limit:
            warnings.append(
                f"max_count {requested} exceeds hard limit {self.max_count_hard_limit}; "
                "clamped to reduce ban / rate-limit risk."
            )
            return self.max_count_hard_limit, warnings
        return max(1, requested), warnings


_settings: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    global _settings
    if _settings is None or refresh:
        load_env_file()
        _settings = Settings()
    return _settings
