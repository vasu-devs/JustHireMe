"""SSRF guard for portfolio import (Tier-0 security fix 0.2)."""
import pytest

from profile.url_guard import BlockedUrlError, assert_public_url, is_public_host


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
