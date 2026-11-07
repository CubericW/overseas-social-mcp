# Overseas Social MCP Server

An **MCP (Model Context Protocol) server** that unifies collection of **public**
data from overseas social platforms behind one set of agent-callable tools, for
Claude Code / Codex / Cursor and any MCP-compatible agent:

| Platform | Backend | API type | Default |
|---|---|---|---|
| **X / Twitter** | [twscrape](https://github.com/vladkens/twscrape) | unofficial (multi-account rotation) | on |
| **Reddit** | [PRAW](https://praw.readthedocs.io) | **official API** ✅ | on (needs keys) |
| **Telegram** | [Telethon](https://docs.telethon.dev) | **official MTProto** ✅ | on (needs keys) |
| **LinkedIn** | [linkedin_scraper](https://github.com/joeyism/linkedin_scraper) | unofficial (**high-risk**) | **off** |

**Graceful degradation**: configure only the platforms you use. If a backend's
dependency or credentials are missing, its tools return a structured
`{ok:false, error:"backend_unavailable", details:[...]}` payload with setup
instructions — the server never crashes.

> ⚠️ **Personal, low-frequency, research use only.** Prefer the official APIs
> (Reddit, Telegram). Unofficial scraping (X, LinkedIn) may violate ToS and get
> accounts restricted — use throwaway accounts and keep volumes tiny.

---

## Tools

| Tool | Platform | Purpose |
|---|---|---|
| `x_search` | X | Search recent tweets by query (supports X operators) |
| `x_user_posts` | X | Recent tweets from a user |
| `reddit_search` | Reddit | Search posts (optionally in one subreddit) |
| `reddit_subreddit_hot` | Reddit | Hot posts of a subreddit |
| `reddit_post_comments` | Reddit | Top comments of a post |
| `telegram_channel_messages` | Telegram | Recent messages of a public channel (optional keyword filter) |
| `linkedin_profile` | LinkedIn | One profile (high-risk) |
| `linkedin_company` | LinkedIn | One company page (high-risk) |
| `list_platforms` | – | Capability matrix |
| `backend_status` | – | Which backends are installed & configured |

All content tools return the **same normalised schema** (identical to the
mediacrawler-mcp wrapper), so the upstream skill treats every platform uniformly:

```json
{
  "ok": true, "platform": "reddit", "count": 12,
  "items": [{
    "id": "...", "author": "...", "author_id": null,
    "content": "...", "like_count": 42, "comment_count": 7,
    "publish_time": 1784473477.0, "url": "https://...",
    "extra": { "...": "platform-specific fields" }, "raw": null
  }],
  "warnings": []
}
```

---

## Install

```bash
# core (always)
pip install --user "mcp>=1.2.0,<2"
# then only the backends you need:
pip install --user twscrape        # X
pip install --user praw            # Reddit
pip install --user telethon        # Telegram
pip install --user linkedin_scraper selenium   # LinkedIn (high-risk)
# or everything:  pip install --user -e ".[all]"
```

## Per-platform setup

### Reddit (official — easiest, lowest risk)
1. Create a **script** app at https://www.reddit.com/prefs/apps .
2. Set `OSMCP_REDDIT_CLIENT_ID`, `OSMCP_REDDIT_CLIENT_SECRET`, `OSMCP_REDDIT_USER_AGENT`.

### Telegram (official)
1. Get `api_id` / `api_hash` at https://my.telegram.org → *API development tools*.
2. Log in once, **yourself**, in a terminal (it prompts for api_id / api_hash,
   phone number, login code and 2FA password):
   ```bash
   cd /path/to/overseas-social-mcp && python3 -m overseas_social_mcp.telegram_login
   ```
   This writes `OSMCP_TG_API_ID` / `OSMCP_TG_API_HASH` / `OSMCP_TG_SESSION` to
   `~/.config/overseas-social-mcp/.env` (chmod 600) and creates
   `~/.config/overseas-social-mcp/telegram.session`. Every server process loads
   that env file at startup, so no secrets go into the MCP client config.
3. `python3 -m overseas_social_mcp.telegram_login --check` verifies the session
   without prompting; `--reset` starts over.

The session is shared by every server process (one per agent session); a file
lock serialises Telegram calls so they don't collide on the SQLite session.

### X / Twitter (twscrape)
1. `pip install --user twscrape`.
2. Add a logged-in account from browser cookies. Copy `auth_token` and `ct0` from
   x.com -> DevTools -> Application -> Cookies, then paste them at the hidden
   prompt as `auth_token=xxx; ct0=yyy`:
   ```bash
   twscrape --db ~/.config/overseas-social-mcp/x_accounts.db add_cookie my_account
   ```
3. Always pass `--db`: the CLI otherwise uses `accounts.db` in the current directory,
   which the server does not read. `OSMCP_X_ACCOUNTS_DB` overrides the path. Use
   throwaway accounts.

`backend_status` reports `accounts_active`. With no active account `x_search` and
`x_user_posts` return `backend_unavailable`, not an empty result.

### LinkedIn (high-risk — off by default)
Only enable with a throwaway account, at your own risk:
`OSMCP_LINKEDIN_ENABLED=true`, `OSMCP_LINKEDIN_EMAIL/PASSWORD`, `OSMCP_CHROMEDRIVER`.

See [`.env.example`](.env.example) for all variables.

---

## Register with an MCP client

### Claude Code
```bash
claude mcp add overseas-social \
  --env PYTHONPATH=/path/to/overseas-social-mcp \
  --env OSMCP_REDDIT_CLIENT_ID=... \
  --env OSMCP_REDDIT_CLIENT_SECRET=... \
  -- python -m overseas_social_mcp.server
```

### Claude Desktop / Cursor
Paste [`examples/claude_desktop_config.snippet.json`](examples/claude_desktop_config.snippet.json)
into your MCP config and fill in the paths/keys.

Run `backend_status` first to confirm what's ready.

---

## Test

```bash
pip install --user pytest
PYTHONPATH=. pytest -q      # no network, no credentials required
```

---

## Safety & compliance

- Prefer official APIs (Reddit, Telegram); they are the compliant path.
- X and LinkedIn backends are unofficial — throwaway accounts, tiny volumes,
  low frequency; you accept the ToS / account risk.
- Do not collect private personal data. Respect platform ToS and local law.
- Built-in guardrails: per-call hard cap, local sliding-window rate limit,
  configurable delays.

---

## License

MIT — see [LICENSE](LICENSE). Backends are optional third-party packages that
you install yourself and are not bundled here: [twscrape](https://github.com/vladkens/twscrape) (MIT),
[PRAW](https://github.com/praw-dev/praw) (BSD-2-Clause), [Telethon](https://github.com/LonamiWebs/Telethon) (MIT),
[linkedin_scraper](https://github.com/joeyism/linkedin_scraper) (GPL-3.0 on GitHub). Each is governed by
its own license.
