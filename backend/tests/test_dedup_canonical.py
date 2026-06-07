"""Canonical, source-independent lead dedup (Tier-1 fix).

The same job URL discovered by scout (raw md5(url)) vs free_scout
(md5(platform:url)) used to produce different ids and slip past dedup. Both now
use canonical_lead_id, so the same posting maps to one row regardless of source.
"""
from discovery.lead_intel import canonical_lead_id, canonical_url


def test_scheme_www_trailing_slash_collapse():
    a = canonical_lead_id("http://www.Example.com/jobs/123/")
    b = canonical_lead_id("https://example.com/jobs/123")
    assert a == b


def test_tracking_params_ignored():
    assert canonical_lead_id("https://ex.com/j/1?utm_source=x&ref=y&gclid=z") == \
           canonical_lead_id("https://ex.com/j/1")


def test_meaningful_query_preserved():
    assert canonical_lead_id("https://b.com/apply?jobId=42") != \
           canonical_lead_id("https://b.com/apply?jobId=99")


def test_query_order_normalized():
    assert canonical_lead_id("https://ex.com/p?b=2&a=1") == \
           canonical_lead_id("https://ex.com/p?a=1&b=2")


def test_distinct_urls_differ():
    assert canonical_lead_id("https://a.com/x") != canonical_lead_id("https://b.com/x")


def test_bare_host_normalized_like_https():
    assert canonical_lead_id("example.com/jobs/1") == \
           canonical_lead_id("https://example.com/jobs/1")


def test_canonical_url_shape():
    assert canonical_url("HTTP://WWW.Example.COM:80/Path/") == "https://example.com/Path"
    assert canonical_url("https://example.com") == "https://example.com/"
    # path case is preserved (only host is lowercased)
    assert "/Path" in canonical_url("https://example.com/Path")


def test_id_is_16_hex():
    cid = canonical_lead_id("https://example.com/jobs/1")
    assert len(cid) == 16 and all(c in "0123456789abcdef" for c in cid)
