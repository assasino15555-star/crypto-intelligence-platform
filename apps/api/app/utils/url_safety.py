from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from ..core.config import get_settings
from ..core.errors import ValidationError

_BLOCKED_HOSTS = {"localhost", "ip6-localhost", "ip6-loopback"}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        if int(ip) in range(
            int(ipaddress.IPv4Address("0.0.0.0")),
            int(ipaddress.IPv4Address("0.255.255.255")) + 1,
        ):
            return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_blocked_ip(ip.ipv4_mapped)
    return False


def assert_safe_outbound_url(url: str, *, allow_http: bool = False) -> None:
    if not url or not isinstance(url, str):
        raise ValidationError("invalid url")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValidationError("invalid url") from exc
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http"):
        raise ValidationError("forbidden scheme")
    if scheme == "http" and not allow_http and not get_settings().is_dev:
        raise ValidationError("http forbidden in production")
    if parsed.username or parsed.password:
        raise ValidationError("credentials in url forbidden")
    host = parsed.hostname or ""
    if not host:
        raise ValidationError("missing host")
    if host.lower() in _BLOCKED_HOSTS:
        raise ValidationError("blocked host")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and _is_blocked_ip(ip):
        raise ValidationError("blocked ip range")


def resolve_and_validate_host(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValidationError(f"dns resolution failed: {exc}") from exc
    ips: list[str] = []
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise ValidationError(f"blocked ip in dns response: {ip}")
        ips.append(str(ip))
    if not ips:
        raise ValidationError("no valid dns addresses")
    return ips


class SafeHttpTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        host = url.host
        if host is None:
            raise ValidationError("missing host")

        try:
            ipaddress.ip_address(host)
            is_ip_literal = True
        except ValueError:
            is_ip_literal = False

        if not is_ip_literal:
            ips = resolve_and_validate_host(str(host))
            validated_ip = ips[0]
            new_url = url.copy_with(host=validated_ip)
            new_headers = request.headers.copy()
            new_headers["host"] = str(host)
            new_extensions: dict[str, Any] = dict(request.extensions)
            new_extensions["sni"] = str(host).encode("ascii")
            request = httpx.Request(
                method=request.method,
                url=new_url,
                headers=new_headers,
                content=request.content,
                extensions=new_extensions,
            )

        return await super().handle_async_request(request)
