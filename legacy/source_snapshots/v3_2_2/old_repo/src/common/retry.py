from __future__ import annotations

import random
import time
from dataclasses import dataclass
from functools import wraps
from logging import Logger
from typing import Callable, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class RetryConfig:
    """
    Configuration for retry behavior.
    """

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True
    exceptions: tuple[type[BaseException], ...] = (Exception,)


def calculate_delay(attempt_number: int, config: RetryConfig) -> float:
    """
    Calculate the retry delay for an attempt.

    attempt_number is 1-based.
    """
    delay = config.initial_delay_seconds * (
        config.backoff_factor ** max(attempt_number - 1, 0)
    )

    delay = min(delay, config.max_delay_seconds)

    if config.jitter:
        delay = random.uniform(0, delay)

    return delay


def validate_retry_config(config: RetryConfig) -> None:
    """
    Validate retry configuration.
    """
    if config.max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if config.initial_delay_seconds < 0:
        raise ValueError("initial_delay_seconds must be non-negative")

    if config.max_delay_seconds < 0:
        raise ValueError("max_delay_seconds must be non-negative")

    if config.backoff_factor < 1:
        raise ValueError("backoff_factor must be at least 1")


def retry_call(
    func: Callable[P, R],
    *args: P.args,
    config: RetryConfig | None = None,
    should_retry: Callable[[BaseException], bool] | None = None,
    logger: Logger | None = None,
    **kwargs: P.kwargs,
) -> R:
    """
    Call a function with retry behavior.
    """
    retry_config = config or RetryConfig()
    validate_retry_config(retry_config)

    retry_filter = should_retry or (lambda exc: isinstance(exc, retry_config.exceptions))

    last_error: BaseException | None = None

    for attempt in range(1, retry_config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except retry_config.exceptions as exc:
            last_error = exc

            should_try_again = attempt < retry_config.max_attempts and retry_filter(exc)

            if not should_try_again:
                raise

            delay = calculate_delay(attempt, retry_config)

            if logger is not None:
                logger.warning(
                    "Retrying after error. attempt=%s max_attempts=%s delay=%.2fs error=%s",
                    attempt,
                    retry_config.max_attempts,
                    delay,
                    exc,
                )

            time.sleep(delay)

    if last_error is not None:
        raise last_error

    raise RuntimeError("retry_call failed without capturing an exception")


def retry(
    *,
    max_attempts: int = 3,
    initial_delay_seconds: float = 1.0,
    max_delay_seconds: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
    logger: Logger | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator for retrying a function.

    Example:
        @retry(max_attempts=3, exceptions=(TimeoutError,))
        def fetch_data():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay_seconds=initial_delay_seconds,
        max_delay_seconds=max_delay_seconds,
        backoff_factor=backoff_factor,
        jitter=jitter,
        exceptions=exceptions,
    )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return retry_call(
                func,
                *args,
                config=config,
                should_retry=should_retry,
                logger=logger,
                **kwargs,
            )

        return wrapper

    return decorator
