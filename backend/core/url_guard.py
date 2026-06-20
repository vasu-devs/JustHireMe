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

# NAT64 well-known prefix (RFC 6052) + RFC 8215 local-use prefix. A DNS64
# resolver on an IPv6-only/dual-stack network synthesises IPv6 addresses that
# embed the real IPv4 destination in the low 32 bits. Python's ipaddress marks
# 64:ff9b::/96 as "reserved", so without unwrapping it the guard would wrongly
# block every legitimately-public host reached via NAT64.
_NAT64_PREFIXES = (
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("64:ff9b:1::/48"),
)


class BlockedUrlError(ValueError):
    """Raised when a URL targets a non-public / internal address (SSRF guard)."""


def _embedded_ipv4(addr: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 embedded in an IPv4-mapped or NAT64 IPv6 address, else None."""
    mapped = addr.ipv4_mapped
    if mapped is not None:
        return mapped
    for prefix in _NAT64_PREFIXES:
        if addr in prefix:
            return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return None


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # NAT64 / IPv4-mapped IPv6 carry a real IPv4 destination — judge that IPv4 so
    # public hosts reached over NAT64 are allowed while a NAT64-wrapped PRIVATE
    # IPv4 (e.g. 64:ff9b::10.0.0.1) is still refused.
    if isinstance(addr, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(addr)
        if embedded is not None:
            addr = embedded
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
