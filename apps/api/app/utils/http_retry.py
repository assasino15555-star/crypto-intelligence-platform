"""HTTP client utilities with retry, backoff, jitter, and 429/Retry-After handling.

Retry policy:
  * Retry only on retryable failures:
      - httpx.TransportError / NetworkError / TimeoutException
      - HTTP 429 (rate-limited) — respect Retry-After
      - HTTP 5xx (provider transient)
  * Do NOT retry permanent 4xx (400/401/403/404)
  * Exponential backoff: base * 2**attempt, capped at 30s, with full jitter
  * Bounded retry count from settings
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from ..core.config import get_settings
from ..core.errors import (
    ProviderError,
    ProviderPermanentError,
    ProviderRetryableError,
    ProviderTimeoutError,
)
from ..core.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

_PERMANENT_STATUS = {400, 401, 403, 404, 422}
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class HttpRetry:
    """Retry wrapper for outbound httpx requests."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        base_backoff: float = 0.5,
        max_backoff: float = 30.0,
    ) -> None:
        s = get_settings()
        self.timeout = timeout if timeout is not None else s.provider_http_timeout
        self.max_retries = max_retries if max_retries is not None else s.provider_max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        """Execute an HTTP request with retry classification."""
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.request(method, url, **kwargs)  # type: ignore[arg-type]
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ProviderTimeoutError(f"timeout: {exc}") from exc
                await self._backoff(attempt, retry_after=None)
                continue
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ProviderRetryableError(f"transport error: {exc}") from exc
                await self._backoff(attempt, retry_after=None)
                continue

            if resp.status_code in _PERMANENT_STATUS:
                raise ProviderPermanentError(f"provider permanent error status={resp.status_code}")
            if resp.status_code in _RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise ProviderRetryableError(
                        f"provider retryable error status={resp.status_code}"
                    )
                retry_after = self._parse_retry_after(resp)
                await self._backoff(attempt, retry_after=retry_after)
                continue
            return resp
        # Should not reach here
        raise ProviderError(f"unreachable retry state: {last_exc}")

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> float | None:
        val = resp.headers.get("Retry-After")
        if not val:
            return None
        try:
            return min(float(val), 60.0)
        except ValueError:
            return None

    async def _backoff(self, attempt: int, *, retry_after: float | None) -> None:
        if retry_after is not None:
            delay = retry_after
        else:
            # Full jitter: uniform(0, min(cap, base * 2**attempt))
            upper = min(self.max_backoff, self.base_backoff * (2**attempt))
            delay = random.uniform(0, upper)
        log.debug("provider retry backoff attempt=%s delay=%.2fs", attempt, delay)
        await asyncio.sleep(delay)


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int | None = None,
    base_backoff: float = 0.5,
) -> T:
    """Generic retry wrapper for async callables that may raise retryable errors."""
    s = get_settings()
    max_retries = max_retries if max_retries is not None else s.provider_max_retries
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except (ProviderRetryableError, ProviderTimeoutError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            upper = min(30.0, base_backoff * (2**attempt))
            await asyncio.sleep(random.uniform(0, upper))
        except ProviderPermanentError:
            raise
    # unreachable
    raise ProviderError(f"unreachable retry state: {last_exc}")
