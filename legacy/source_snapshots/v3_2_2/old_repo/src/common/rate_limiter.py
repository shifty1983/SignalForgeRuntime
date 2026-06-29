from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from functools import wraps
from threading import Lock
from typing import Callable, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class RateLimitConfig:
    """
    Configuration for rate limiting.

    Example:
        RateLimitConfig(calls=5, period_seconds=60)
    """

    calls: int
    period_seconds: float = 60.0


class RateLimiter:
    """
    Simple thread-safe sliding-window rate limiter.

    Example:
        limiter = RateLimiter(calls=5, period_seconds=60)

        with limiter:
            fetch_data()
    """

    def __init__(
        self,
        calls: int,
        period_seconds: float = 60.0,
        *,
        name: str | None = None,
    ) -> None:
        if calls < 1:
            raise ValueError("calls must be at least 1")

        if period_seconds <= 0:
            raise ValueError("period_seconds must be greater than 0")

        self.calls = calls
        self.period_seconds = period_seconds
        self.name = name or "rate_limiter"

        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def acquire(self, *, block: bool = True) -> bool:
        """
        Acquire permission to proceed.

        If block=True, waits until a slot is available.
        If block=False, returns False when rate limited.
        """
        while True:
            wait_seconds = 0.0

            with self._lock:
                now = time.monotonic()

                while self._timestamps and now - self._timestamps[0] >= self.period_seconds:
                    self._timestamps.popleft()

                if len(self._timestamps) < self.calls:
                    self._timestamps.append(now)
                    return True

                if not block:
                    return False

                oldest_timestamp = self._timestamps[0]
                wait_seconds = self.period_seconds - (now - oldest_timestamp)

            time.sleep(max(wait_seconds, 0.0))

    def __enter__(self) -> RateLimiter:
        self.acquire(block=True)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def limit(self, func: Callable[P, R]) -> Callable[P, R]:
        """
        Decorate a function with this rate limiter.
        """

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            self.acquire(block=True)
            return func(*args, **kwargs)

        return wrapper


def rate_limited(
    *,
    calls: int,
    period_seconds: float = 60.0,
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory for rate limiting.

    Example:
        @rate_limited(calls=5, period_seconds=60)
        def fetch_data():
            ...
    """
    limiter = RateLimiter(
        calls=calls,
        period_seconds=period_seconds,
        name=name,
    )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return limiter.limit(func)

    return decorator


def per_second(calls: int, *, name: str | None = None) -> RateLimiter:
    """
    Create a rate limiter for calls per second.
    """
    return RateLimiter(calls=calls, period_seconds=1.0, name=name)


def per_minute(calls: int, *, name: str | None = None) -> RateLimiter:
    """
    Create a rate limiter for calls per minute.
    """
    return RateLimiter(calls=calls, period_seconds=60.0, name=name)


def per_hour(calls: int, *, name: str | None = None) -> RateLimiter:
    """
    Create a rate limiter for calls per hour.
    """
    return RateLimiter(calls=calls, period_seconds=3600.0, name=name)
