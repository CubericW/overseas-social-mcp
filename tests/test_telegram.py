"""Telegram backend helpers and env-file loading (no network, no creds)."""

import os

import pytest

from overseas_social_mcp.backends import telegram_backend
from overseas_social_mcp.common import BackendUnavailable
from overseas_social_mcp.config import Settings, load_env_file


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("durov", "durov"),
        ("@durov", "durov"),
        ("https://t.me/durov", "durov"),
        ("t.me/s/durov", "durov"),
        ("https://t.me/durov/123?single", "durov"),
        ("https://telegram.me/durov/", "durov"),
        ("https://t.me/c/1234567890/55", -1001234567890),
        ("-1001234567890", -1001234567890),
        ("https://t.me/+AbCdEf123", "https://t.me/+AbCdEf123"),
    ],
)
def test_normalize_channel(raw, expected):
    assert telegram_backend.normalize_channel(raw) == expected


def test_normalize_channel_rejects_empty():
    with pytest.raises(ValueError):
        telegram_backend.normalize_channel("  @ ")


def test_session_file_appends_suffix(tmp_path):
    s = Settings()
    s.telegram_session = str(tmp_path / "tg")
    assert telegram_backend.session_file(s) == str(tmp_path / "tg.session")
    s.telegram_session = str(tmp_path / "tg.session")
    assert telegram_backend.session_file(s) == str(tmp_path / "tg.session")


def test_missing_session_is_backend_unavailable(tmp_path):
    s = Settings()
    s.telegram_api_id, s.telegram_api_hash = "12345", "0" * 32
    s.telegram_session = str(tmp_path / "absent.session")
    with pytest.raises(BackendUnavailable, match="telegram_login"):
        telegram_backend.channel_messages(s, "durov", 5)
    assert not os.path.exists(s.telegram_session)  # no stray empty session created


def test_load_env_file_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nexport OSMCP_T_A=from_file\nOSMCP_T_B="quoted"\nOSMCP_T_C=from_file\n\n')
    monkeypatch.delenv("OSMCP_T_A", raising=False)
    monkeypatch.delenv("OSMCP_T_B", raising=False)
    monkeypatch.setenv("OSMCP_T_C", "from_client")
    load_env_file(str(env))
    assert os.environ["OSMCP_T_A"] == "from_file"
    assert os.environ["OSMCP_T_B"] == "quoted"
    assert os.environ["OSMCP_T_C"] == "from_client"
    for key in ("OSMCP_T_A", "OSMCP_T_B"):
        monkeypatch.delenv(key)


def test_session_lock_excludes_second_holder(tmp_path):
    path = str(tmp_path / "s.session")
    with telegram_backend.session_lock(path, timeout=1):
        with pytest.raises(RuntimeError, match="busy"):
            with telegram_backend.session_lock(path, timeout=0.3):
                pass
    with telegram_backend.session_lock(path, timeout=1):  # released again
        pass
