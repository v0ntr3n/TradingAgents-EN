"""
Unified retry tool

Provides retryable exception judgment and synchronous/asynchronous exponential backoff retry functions.
For sharing by UnifiedLLMClient, AgentBase and other modules.
"""

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_KEYWORDS = (
    "choices", "null value", "connection", "timeout", "timed out",
    "rate limit", "too many requests", "server error", "500", "502", "503", "529",
    # Current limiting tips for domestic gateways such as JD Cloud
    "429", "rate_limit", "tokens limit", "rate_limited", "Access restrictions", "RATE_LIMIT",
)


def is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(kw in msg for kw in RETRYABLE_KEYWORDS)


def retry_sync(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    max_wait: int = 10,
    label: str = "retry_sync",
    retryable: Optional[Callable[[Exception], bool]] = None,
    **kwargs: Any,
) -> T:
    """Synchronous exponential backoff retries.

    Args:
        fn: The callable to retry
        max_retries: Maximum number of retries (excluding first call)
        max_wait: Backoff upper limit seconds
        label: log tag
        retryable: Customized retryable judgment function, used by default is_retryable
    """
    _retryable = retryable or is_retryable
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # exponential backoff + Random jitter to avoid multiple requests synchronously retrying to form a storm (such as 429 current limiting scenario)
                wait = min(2 ** attempt, max_wait) + random.uniform(0, 1)
                logger.info("[%s] Wait for %.1fs and try again (%d/%d)...", label, wait, attempt, max_retries)
                time.sleep(wait)
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _retryable(e) and attempt < max_retries:
                logger.warning("[%s] The call failed (can be retried): %s", label, e)
                continue
            raise
    raise last_err  # type: ignore[misc]  # pragma: no cover


async def retry_async(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    max_wait: int = 10,
    label: str = "retry_async",
    retryable: Optional[Callable[[Exception], bool]] = None,
    **kwargs: Any,
) -> T:
    """Asynchronous exponential backoff retries."""
    _retryable = retryable or is_retryable
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # exponential backoff + Random jitter to avoid multiple requests synchronously retrying to form a storm (such as 429 current limiting scenario)
                wait = min(2 ** attempt, max_wait) + random.uniform(0, 1)
                logger.info("[%s] Wait for %.1fs and try again (%d/%d)...", label, wait, attempt, max_retries)
                await asyncio.sleep(wait)
            return await fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _retryable(e) and attempt < max_retries:
                logger.warning("[%s] The call failed (can be retried): %s", label, e)
                continue
            raise
    raise last_err  # type: ignore[misc]  # pragma: no cover
