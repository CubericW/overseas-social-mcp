"""Overseas Social MCP Server.

An MCP (Model Context Protocol) server that unifies collection of PUBLIC data
from overseas social platforms behind one set of agent-callable tools:

    X / Twitter   (via twscrape)
    Reddit        (via PRAW, official API)
    Telegram      (via Telethon, official MTProto)
    LinkedIn      (via linkedin_scraper, best-effort)

Each backend degrades gracefully: if its optional dependency or credentials are
missing, the tool returns a structured, actionable error instead of crashing.

For personal, low-frequency, research use only. Prefer official APIs
(Reddit / Telegram) and respect each platform's Terms of Service.
"""

__version__ = "0.1.0"
