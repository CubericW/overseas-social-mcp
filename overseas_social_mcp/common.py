"""Shared helpers: rate limiter and a stable output schema.

The normalised record schema is intentionally identical in spirit to the
mediacrawler-mcp wrapper so the upstream skill can treat every platform the
same way.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self.max_calls = max(1, max_calls)
        self.window_seconds = max(1, window_seconds)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> tuple[bool, float]:
        now = time.time()
        with self._lock:
            cutoff = now - self.window_seconds
            while self._calls and self._calls[0] < cutoff:
                self._calls.popleft()
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return True, 0.0
            return False, max(0.0, self.window_seconds - (now - self._calls[0]))


def make_item(
    *,
    id: str | None,
    author: str | None,
    author_id: str | None = None,
    content: str | None,
    like_count: Any = None,
    comment_count: Any = None,
    publish_time: Any = None,
    url: str | None = None,
    extra: dict[str, Any] | None = None,
    raw: Any = None,
) -> dict[str, Any]:
    """Build one normalised item with the shared cross-platform schema."""
    return {
        "id": id,
        "author": author,
        "author_id": author_id,
        "content": content,
        "like_count": like_count,
        "comment_count": comment_count,
        "publish_time": publish_time,
        "url": url,
        "extra": extra or {},
        "raw": raw,
    }


def ok_result(platform: str, platform_name: str, items: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    out = {
        "ok": True,
        "platform": platform,
        "platform_name": platform_name,
        "count": len(items),
        "items": items,
        "warnings": kw.pop("warnings", []),
    }
    out.update(kw)
    return out


def err_result(error: str, details: list[str]) -> dict[str, Any]:
    return {"ok": False, "error": error, "details": details}


class BackendUnavailable(RuntimeError):
    """Raised when a backend's optional dependency or credentials are missing."""
