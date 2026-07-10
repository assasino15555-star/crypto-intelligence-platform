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
    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        base_backoff: float = 0.5,
        max_backoff: float = 30.0,
        max_response_bytes: int | None = None,
    ) -> None:
        s = get_settings()
        self.timeout = timeout if timeout is not None else s.provider_http_timeout
        self.max_retries = max_retries if max_retries is not None else s.provider_max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.max_response_bytes = (
            max_response_bytes if max_response_bytes is not None else s.provider_max_response_bytes
        )

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._streaming_request(client, method, url, **kwargs)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ProviderTimeoutError("provider timeout") from exc
                await self._backoff(attempt, retry_after=None)
                continue
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ProviderRetryableError("provider transport error") from exc
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
                await resp.aclose()
                await self._backoff(attempt, retry_after=retry_after)
                continue
            return resp
        raise ProviderError(f"unreachable retry state: {last_exc}")

    async def _streaming_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        req = client.build_request(method, url, **kwargs)  # type: ignore[arg-type]
        resp = await client.send(req, stream=True)

        content_length = resp.headers.get("Content-Length")
        if content_length:
            try:
                size = int(content_length)
            except ValueError:
                size = -1
            if size > self.max_response_bytes:
                await resp.aclose()
                raise ProviderPermanentError(
                    f"response too large: {size} > {self.max_response_bytes}"
                )

        body = bytearray()
        max_bytes = self.max_response_bytes
        try:
            async for chunk in resp.aiter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > max_bytes:
                    await resp.aclose()
                    raise ProviderPermanentError(f"response body exceeded {max_bytes} bytes")
        except httpx.TransportError:
            await resp.aclose()
            raise
        except ProviderPermanentError:
            raise

        await resp.aclose()

        return httpx.Response(
            status_code=resp.status_code,
            headers=resp.headers,
            content=bytes(body),
            request=resp.request,
        )

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> float | None:
        val = resp.headers.get("Retry-After")
        if not val:
            return None
        try:
            parsed = float(val)
        except ValueError:
            return None
        return max(0.0, min(parsed, 60.0))

    async def _backoff(self, attempt: int, *, retry_after: float | None) -> None:
        if retry_after is not None:
            delay = retry_after
        else:
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
    raise ProviderError(f"unreachable retry state: {last_exc}")


def assert_json_content_type(resp: httpx.Response) -> None:
    ct = resp.headers.get("Content-Type", "")
    if "application/json" not in ct.lower():
        raise ProviderPermanentError(f"unexpected content-type: {ct[:60]}")
