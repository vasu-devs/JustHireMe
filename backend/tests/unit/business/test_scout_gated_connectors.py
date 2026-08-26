"""Routing + gated-connector tests for the board scout (automation.scout.run).

Covers two fixes made for the SOTA initiative:

1. **Remotive** keyless API is now routed to its dedicated keyless scraper
   (`_scrape_remotive`) instead of silently falling through to the browser/LLM
   web path. RemoteOK / Remotive / Jobicy are all default keyless boards and
   must work zero-config.

2. **Apify** (a GATED connector: requires apify_token + apify_actor) was DEAD —
   `scout.run` only invoked the actor when a `queries` arg was passed, but no
   caller ever populated it. The actor now receives queries derived from the
   `site:` dork targets (exactly the targets the keyless API/RSS path can't
   serve). This test proves the actor is genuinely invoked with those queries
   when the connector is configured.

Network/DB are isolated: the keyless scraper and the Apify call are mocked, and
the module-level persistence hooks (`url_exists` / `save_lead`) are stubbed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import pytest

from automation import scout

pytestmark = pytest.mark.integration


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_remotive_api_routed_to_keyless_scraper():
    """A remotive.com/api target hits the keyless Remotive scraper (not web)."""
    called = {}

    async def fake_remotive(u):
        called["u"] = u
        return [{
            "title": "Registered Nurse",
            "company": "Charité Berlin",
            "url": "https://remotive.com/remote-jobs/nurse-123",
            "platform": "remotive",
            "description": (
                "Charité Berlin is hiring a registered nurse for a full-time onsite "
                "role in Berlin, Germany. Patient care, medication administration, "
                "and ward coordination. Apply now with your nursing license."
            ),
            "posted_date": _now_iso(),
            "source_meta": {"source": "remotive"},
        }]

    with (
        mock.patch.object(scout, "_scrape_remotive", fake_remotive),
        # Make sure it does NOT fall through to the web/browser path.
        mock.patch.object(scout.web_sources, "scrape", lambda *a, **k: (_ for _ in ()).throw(AssertionError("web path used"))),
        mock.patch.object(scout, "url_exists", lambda _jid: False),
        mock.patch.object(scout, "save_lead", lambda *a, **k: None),
    ):
        leads = scout.run(urls=["https://remotive.com/api/remote-jobs"])

    assert called.get("u") == "https://remotive.com/api/remote-jobs", "remotive target was not routed to the keyless scraper"
    # The non-tech, non-US lead survives the neutral quality gate end-to-end.
    assert any(lead.get("platform") == "remotive" for lead in leads), f"no remotive lead returned: {leads}"
    blob = " ".join((lead.get("title", "") + " " + lead.get("description", "")) for lead in leads).lower()
    assert "nurse" in blob and ("berlin" in blob or "germany" in blob)


def test_apify_gated_invokes_actor_with_derived_queries():
    """When apify_token + apify_actor are configured, the (previously dead) Apify
    branch invokes the actor with queries DERIVED from the site: dork targets."""
    captured = {}

    async def fake_apify(actor, inp, tok):
        captured["actor"] = actor
        captured["inp"] = inp
        captured["tok"] = tok
        return [{
            "title": "Welder",
            "company": "SteelWorks",
            "url": "https://example.test/jobs/welder-apify",
        }]

    with (
        mock.patch.object(scout, "apify", fake_apify),
        # site: targets would otherwise hit the browser/LLM web path; stub it out.
        mock.patch.object(scout.web_sources, "scrape", lambda *a, **k: []),
        mock.patch.object(scout, "url_exists", lambda _jid: False),
        mock.patch.object(scout, "save_lead", lambda *a, **k: None),
    ):
        scout.run(
            urls=["site:linkedin.com/jobs welder", "site:indeed.com/jobs nurse"],
            apify_token="tok-123",
            apify_actor="acme/job-actor",
        )

    assert captured.get("actor") == "acme/job-actor", "Apify actor was not invoked (dead path not revived)"
    assert captured.get("tok") == "tok-123"
    assert captured.get("inp", {}).get("queries") == [
        "linkedin.com/jobs welder",
        "indeed.com/jobs nurse",
    ], f"actor did not receive site-derived queries: {captured.get('inp')}"


def test_apify_not_invoked_without_credentials():
    """No token/actor ⇒ the gated Apify connector stays off (no actor call)."""
    invoked = {"called": False}

    async def fake_apify(actor, inp, tok):
        invoked["called"] = True
        return []

    with (
        mock.patch.object(scout, "apify", fake_apify),
        mock.patch.object(scout.web_sources, "scrape", lambda *a, **k: []),
        mock.patch.object(scout, "url_exists", lambda _jid: False),
        mock.patch.object(scout, "save_lead", lambda *a, **k: None),
    ):
        scout.run(urls=["site:linkedin.com/jobs welder"])  # no apify creds

    assert invoked["called"] is False, "Apify actor must not run without token+actor"
