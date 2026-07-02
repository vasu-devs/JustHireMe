"""The apify actor is interpolated into the request path, so it must be
allowlisted to stop a configured actor from reshaping the acts/... URL
(path traversal / host smuggling)."""

import asyncio

import pytest

from discovery.sources.apify import _ACTOR_RE, run_actor


@pytest.mark.unit
@pytest.mark.parametrize(
    "actor",
    [
        "apify/web-scraper",
        "apify.cheerio-scraper",
        "user.actor-name_v2",
        "apify",
    ],
)
def test_actor_regex_accepts_well_formed(actor):
    assert _ACTOR_RE.match(actor)


@pytest.mark.unit
@pytest.mark.parametrize(
    "actor",
    [
        "../apify",  # path traversal
        "a/b/c",  # too deep for acts/<owner>/<name>
        "",  # empty
        "evil host",  # whitespace
        "apify/../x",  # traversal mid-string
        "apify web",  # space
    ],
)
def test_actor_regex_rejects_malformed(actor):
    assert not _ACTOR_RE.match(actor)


@pytest.mark.unit
def test_run_actor_raises_on_traversal_actor():
    # Validation runs before the HTTP client is used, so this never touches the
    # network — it proves the guard is wired into run_actor, not a dead regex.
    with pytest.raises(ValueError):
        asyncio.run(run_actor("../evil", {}, "tok"))


@pytest.mark.unit
def test_run_actor_raises_on_empty_actor():
    with pytest.raises(ValueError):
        asyncio.run(run_actor("", {}, "tok"))
