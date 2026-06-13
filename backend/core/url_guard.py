"""SSRF guard for user-supplied URLs (portfolio import).

The portfolio importer fetches an arbitrary URL the user types, follows
same-origin links, and (in the HTTP fallback) follows redirects. Without a guard
that lets a user — or a malicious page redirect — drive the backend into fetching
internal services (``127.0.0.1``, cloud metadata at ``169.254.169.254``, private
LAN hosts) and exfiltrating their content via the returned screenshot/text.

This module resolves a host's IPs and refuses anything that is not a public
unicast address. It is applied to every URL the crawlers fetch, including
redirect targets, so same-origin expansion and redirects cannot reach internal
hosts.

Residual risk: DNS rebinding (a host that resolves public here but private at
connect time) is only partially mitigated by requiring *all* resolved records to
be public; fully closing it would require pinning the resolved IP for the
connection. Documented intentionally.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("http", "https")


class BlockedUrlError(ValueError):
    """Raised when a URL targets a non-public / internal address (SSRF guard)."""


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # is_link_local covers 169.254.0.0/16 (incl. cloud metadata) and fe80::/10.
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def is_public_host(host: str) -> bool:
    """True only if ``host`` is (or resolves entirely to) public unicast IPs."""
    if not host:
        return False
    # Bracketed IPv6 literals arrive as "[::1]" from some parsers.
    host = host.strip().strip("[]")
    # Literal IP: check it directly, no DNS.
    try:
        ipaddress.ip_address(host)
        return _ip_is_public(host)
    except ValueError:
        pass
    # Hostname: every resolved address must be public (partial rebinding guard).
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    addrs = {info[4][0] for info in infos}
    return bool(addrs) and all(_ip_is_public(a) for a in addrs)


def assert_public_url(url: str) -> str:
    """Return ``url`` if it is an http(s) URL to a public host; else raise."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise BlockedUrlError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise BlockedUrlError("URL has no host")
    if not is_public_host(host):
        raise BlockedUrlError(f"refusing to fetch non-public host: {host!r}")
    return url
