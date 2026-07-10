from __future__ import annotations

import ipaddress
import secrets
import time
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis_lib

from ..core.config import get_settings
from ..core.errors import RateLimitError
from ..core.logging import get_logger

log = get_logger(__name__)

_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local capacity = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])

local window_start = now - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local count = redis.call('ZCARD', key)

if count >= capacity then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if oldest[2] ~= nil then
        local retry_after = math.ceil((tonumber(oldest[2]) + window_ms - now) / 1000)
        if retry_after < 1 then retry_after = 1 end
        return {0, retry_after}
    end
    return {0, math.ceil(window_ms / 1000)}
end

redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, ttl)
return {1, 0}
"""


@dataclass(frozen=True)
class LimitSpec:
    capacity: int
    window_seconds: int

    @property
    def key_suffix(self) -> str:
        return f"{self.capacity}:{self.window_seconds}"


LOGIN_IP = LimitSpec(capacity=5, window_seconds=60)
LOGIN_USER = LimitSpec(capacity=10, window_seconds=60)
AI_USER = LimitSpec(capacity=10, window_seconds=60)
AI_GLOBAL = LimitSpec(capacity=100, window_seconds=60)
SNAPSHOT_USER = LimitSpec(capacity=10, window_seconds=60)
WALLET_CREATE_USER = LimitSpec(capacity=10, window_seconds=60)
ALERT_CREATE_USER = LimitSpec(capacity=20, window_seconds=60)
GLOBAL_REQUEST = LimitSpec(capacity=200, window_seconds=60)

_POOL: Any = None
_LUA_SHA: str | None = None


def _get_pool() -> Any:
    global _POOL
    if _POOL is None:
        settings = get_settings()
        _POOL = redis_lib.ConnectionPool.from_url(
            str(settings.redis_url),
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _POOL


def _get_redis() -> Any:
    return redis_lib.Redis(connection_pool=_get_pool())


async def close_pool() -> None:
    global _POOL, _LUA_SHA
    if _POOL is not None:
        await _POOL.disconnect()
        _POOL = None
        _LUA_SHA = None


class RedisRateLimiter:
    def __init__(self, spec: LimitSpec) -> None:
        self.spec = spec

    async def check(self, key: str) -> None:
        global _LUA_SHA
        full_key = f"rl:{key}:{self.spec.key_suffix}"
        now_ms = int(time.time() * 1000)
        window_ms = self.spec.window_seconds * 1000
        member = f"{now_ms}:{secrets.token_hex(8)}"
        ttl_ms = (self.spec.window_seconds + 1) * 1000

        client = _get_redis()
        try:
            if _LUA_SHA is None:
                _LUA_SHA = await client.script_load(_RATE_LIMIT_LUA)

            result = await client.evalsha(
                _LUA_SHA,
                1,
                full_key,
                now_ms,
                window_ms,
                self.spec.capacity,
                member,
                ttl_ms,
            )
        except Exception as exc:
            if "NOSCRIPT" in str(exc):
                _LUA_SHA = None
                return await self.check(key)
            log.warning("rate limiter redis error, failing closed: %s", exc)
            raise RateLimitError("rate limit unavailable") from exc

        allowed = int(result[0])
        if allowed == 0:
            retry_after = int(result[1])
            raise RateLimitError(
                "rate limited",
                code="rate_limited",
                retry_after=retry_after,
            )


def _parse_trusted_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    settings = get_settings()
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in settings.rate_limit_trusted_proxies:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            try:
                ip = ipaddress.ip_address(entry)
                networks.append(
                    ipaddress.ip_network(f"{ip}/32" if ip.version == 4 else f"{ip}/128")
                )
            except ValueError:
                log.warning("invalid trusted proxy entry: %s", entry)
    return networks


def _ip_in_networks(
    ip_str: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]
) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def trusted_client_ip(request: object) -> str:
    client = getattr(request, "client", None)
    direct_ip = ""
    if client is not None:
        host = getattr(client, "host", None)
        if isinstance(host, str) and host:
            direct_ip = host

    trusted_networks = _parse_trusted_networks()
    if not trusted_networks:
        return direct_ip or "unknown"

    xff = _header(request, "X-Forwarded-For")
    if not xff:
        return direct_ip or "unknown"

    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if not parts:
        return direct_ip or "unknown"

    current = direct_ip
    for hop in reversed(parts):
        if not current or _ip_in_networks(current, trusted_networks):
            current = hop
        else:
            break

    if current and _is_valid_ip(current):
        return current
    return direct_ip or "unknown"


def _is_valid_ip(ip_str: str) -> bool:
    try:
        ipaddress.ip_address(ip_str)
        return True
    except ValueError:
        return False


def _header(request: object, name: str) -> str:
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    v = headers.get(name) if hasattr(headers, "get") else None
    return v if isinstance(v, str) else ""


class InMemoryRateLimiter:
    def __init__(self, spec: LimitSpec) -> None:
        self.spec = spec
        self._timestamps: dict[str, list[float]] = {}

    async def check(self, key: str) -> None:
        now = time.time()
        window_start = now - self.spec.window_seconds
        entries = self._timestamps.get(key, [])
        entries = [t for t in entries if t > window_start]
        if len(entries) >= self.spec.capacity:
            oldest = entries[0]
            retry_after = max(1, int(oldest + self.spec.window_seconds - now))
            raise RateLimitError(
                "rate limited",
                code="rate_limited",
                retry_after=retry_after,
            )
        entries.append(now)
        self._timestamps[key] = entries
        if len(self._timestamps) > 10_000:
            self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self.spec.window_seconds
        for k in list(self._timestamps):
            self._timestamps[k] = [t for t in self._timestamps[k] if t > cutoff]
            if not self._timestamps[k]:
                del self._timestamps[k]


def make_limiter(spec: LimitSpec) -> RedisRateLimiter | InMemoryRateLimiter:
    settings = get_settings()
    if not settings.is_production:
        return InMemoryRateLimiter(spec)
    return RedisRateLimiter(spec)
