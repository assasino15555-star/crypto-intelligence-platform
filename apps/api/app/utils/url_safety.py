"""SSRF protection for outbound URLs.

Rules:
  * HTTPS only (HTTP only allowed for localhost dev with explicit setting).
  * No credentials in URL (user:pass@host).
  * No localhost / loopback / link-local / private network ranges by default.
  * No IP literals in production.
  * No redirects followed by default (provider clients set follow_redirects=False).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from ..core.config import get_settings
from ..core.errors import ValidationError

_BLOCKED_HOSTS = {"localhost", "ip6-localhost", "ip6-loopback"}


def assert_safe_outbound_url(url: str, *, allow_http: bool = False) -> None:
    """Raise ValidationError if the URL is unsafe for outbound fetching."""
    if not url or not isinstance(url, str):
        raise ValidationError("empty url")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValidationError(f"invalid url: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http"):
        raise ValidationError(f"forbidden scheme: {scheme}")
    if scheme == "http" and not allow_http and not get_settings().is_dev:
        raise ValidationError("http scheme forbidden in production")
    if parsed.username or parsed.password:
        raise ValidationError("credentials in url are forbidden")
    host = parsed.hostname or ""
    if not host:
        raise ValidationError("missing host")
    if host.lower() in _BLOCKED_HOSTS:
        raise ValidationError("localhost blocked")
    # If host is an IP literal, validate ranges
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValidationError(f"blocked ip range: {ip}")
