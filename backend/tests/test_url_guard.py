"""SSRF guard for portfolio import (Tier-0 security fix 0.2)."""
import pytest

from core.url_guard import BlockedUrlError, assert_public_url, is_public_host


@pytest.mark.parametrize("ip", [
    "8.8.8.8",        # public unicast
    "1.1.1.1",
    "93.184.216.34",  # example.com
])
def test_public_ip_literals_allowed(ip):
    assert is_public_host(ip) is True


@pytest.mark.parametrize("ip", [
    "127.0.0.1",        # loopback
    "0.0.0.0",          # unspecified
    "10.0.0.5",         # private
    "172.16.4.4",       # private
    "192.168.1.10",     # private
    "169.254.169.254",  # link-local / cloud metadata
    "::1",              # ipv6 loopback
    "fe80::1",          # ipv6 link-local
    "fc00::1",          # ipv6 unique-local (private)
])
def test_internal_ip_literals_blocked(ip):
    assert is_public_host(ip) is False


@pytest.mark.parametrize("addr", [
    "64:ff9b::808:808",    # NAT64 (RFC 6052) of public 8.8.8.8 — DNS64 networks synthesise these
    "64:ff9b::101:101",    # NAT64 of public 1.1.1.1
    "64:ff9b:1::808:808",  # RFC 8215 local-use NAT64 prefix of 8.8.8.8
    "::ffff:8.8.8.8",      # IPv4-mapped public
])
def test_nat64_and_mapped_public_allowed(addr):
    # A DNS64/NAT64 resolver returns these for public hosts; the guard must judge
    # the embedded IPv4 (public) and ALLOW, not treat 64:ff9b::/96 as "reserved".
    assert is_public_host(addr) is True


@pytest.mark.parametrize("addr", [
    "64:ff9b::a00:1",       # NAT64 of private 10.0.0.1
    "64:ff9b::7f00:1",      # NAT64 of loopback 127.0.0.1
    "64:ff9b::a9fe:a9fe",   # NAT64 of cloud-metadata 169.254.169.254
    "::ffff:10.0.0.1",      # IPv4-mapped private
    "::ffff:127.0.0.1",     # IPv4-mapped loopback
])
def test_nat64_and_mapped_internal_blocked(addr):
    # SSRF protection must survive the NAT64 unwrap: a NAT64/mapped wrapper around
    # an internal IPv4 is still refused.
    assert is_public_host(addr) is False


def test_localhost_hostname_blocked():
    # Resolves to loopback — must be refused even though it's a name, not an IP.
    assert is_public_host("localhost") is False


def test_unresolvable_host_blocked():
    assert is_public_host("definitely-not-a-real-host.invalid") is False


def test_empty_host_blocked():
    assert is_public_host("") is False


def test_assert_public_url_rejects_loopback():
    with pytest.raises(BlockedUrlError):
        assert_public_url("http://127.0.0.1:8000/admin")


def test_assert_public_url_rejects_metadata():
    with pytest.raises(BlockedUrlError):
        assert_public_url("http://169.254.169.254/latest/meta-data/")


def test_assert_public_url_rejects_non_http_scheme():
    with pytest.raises(BlockedUrlError):
        assert_public_url("file:///etc/passwd")
    with pytest.raises(BlockedUrlError):
        assert_public_url("gopher://127.0.0.1/")


def test_assert_public_url_rejects_no_host():
    with pytest.raises(BlockedUrlError):
        assert_public_url("http:///nohost")


def test_assert_public_url_allows_public():
    assert assert_public_url("https://8.8.8.8/") == "https://8.8.8.8/"
