"""Mock and OpenAI-compatible AI providers."""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import AiProviderError
from ..core.logging import get_logger
from ..utils.http_retry import HttpRetry
from .prompt import AiProvider

log = get_logger(__name__)


class MockAiProvider:
    name = "mock"

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        try:
            data = json.loads(user)
        except ValueError:
            data = {}
        chain = data.get("chain", "unknown")
        addr = data.get("address", "")
        label = data.get("label") or "(no label)"
        txs = data.get("recent_transactions", []) or []
        tx_summary = f"{len(txs)} recent transactions" if txs else "no recent transactions"
        return (
            f"Factual data: wallet on {chain} at {addr[:10]}... ({label}) shows "
            f"{tx_summary}. Interpretation: based on the on-chain activity alone, "
            "this wallet appears to be a normal user wallet; no anomalies are present "
            "in the bounded snapshot provided. This is an automated interpretation, "
            "not financial advice."
        )


class OpenAiProvider:
    name = "openai"

    def __init__(self) -> None:
        s = get_settings()
        if not s.ai_api_key:
            raise AiProviderError("AI_API_KEY required for openai provider")
        self._api_key = s.ai_api_key
        self._base_url = s.ai_base_url.rstrip("/")
        self._model = s.ai_model
        self._timeout = s.ai_http_timeout
        self._retry = HttpRetry(timeout=self._timeout, max_retries=2)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                follow_redirects=False,
            )
        return self._client

    async def complete(self, system: str, user: str, *, max_tokens: int) -> str:
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        try:
            resp = await self._retry.request(
                client, "POST", f"{self._base_url}/chat/completions", json=body, headers=headers
            )
        except Exception as exc:
            raise AiProviderError(f"openai request failed: {exc}") from exc
        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise AiProviderError("openai non-json response") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AiProviderError(f"openai malformed response: {exc}") from exc
        if not isinstance(content, str):
            raise AiProviderError("openai returned non-string content")
        return content

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_provider: AiProvider | None = None


def get_ai_provider() -> AiProvider:
    global _provider
    if _provider is None:
        s = get_settings()
        if s.ai_provider == "openai":
            _provider = OpenAiProvider()
        elif s.ai_provider == "mock":
            _provider = MockAiProvider()
        else:
            raise AiProviderError(f"unknown AI_PROVIDER: {s.ai_provider}")
    return _provider


def reset_ai_provider() -> None:
    global _provider
    _provider = None
