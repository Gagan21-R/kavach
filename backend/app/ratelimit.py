"""In-process sliding-window rate limiter.

Limitation: state is per process, so it does not hold across multiple workers or restarts.
Swap for a shared store (e.g. Redis) before running more than one instance.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.config import get_settings
from app.errors import APIError

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def reset() -> None:
    with _lock:
        _hits.clear()


def check(key: str, limit: int, window_seconds: float = 60.0) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise APIError(429, "RATE_LIMITED", "too many attempts, try again later")
        q.append(now)


def auth_limit(request: Request) -> None:
    # The Red Team Lab runs its own isolated, in-memory app instance and flags it; real traffic never sets this.
    if getattr(request.app.state, "ratelimit_exempt", False):
        return
    ip = request.client.host if request.client else "unknown"
    check(f"auth:{request.url.path}:{ip}", get_settings().rate_limit_auth_per_minute)
