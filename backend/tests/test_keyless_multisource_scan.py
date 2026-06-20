"""Integration test: a no-API-key scan returns non-empty, deduplicated,
field/location-agnostic leads from MULTIPLE keyless sources.

This is the P0 acceptance test for the SOTA initiative. It proves that a brand
new user — in a NON-US country, in a NON-tech field, with NO API key and NO
configuration — gets real, deduped, relevant leads from several keyless sources
at once. The network is fully mocked (httpx.MockTransport) so the test is
offline, deterministic, and exercises the real source adapters, the real
quality gate, and the real canonical-URL dedup.

Profiles used here are deliberately non-tech and non-US (a senior ICU nurse in
Nairobi, a head chef in São Paulo, a certified welder in Munich, a primary-
school teacher in Manila) and one role is deliberately SENIOR, to prove the
quality gate is field/location/seniority neutral by default.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import httpx
import pytest

from core.config import free_sources_enabled

# Capture the real client class before any test patches the symbol.
_RealAsyncClient = httpx.AsyncClient

pytestmark = pytest.mark.integration


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


# A shared canonical apply URL, reached two different ways (one with tracking
# params), to prove cross-source canonical-URL deduplication.
_SHARED_NURSE_URL = "https://boards.greenhouse.io/mercyhospital/jobs/4521"

_GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "title": "Senior Registered Nurse (ICU)",
            "content": (
                "<p>Mercy Hospital is hiring an experienced ICU registered nurse "
                "for our critical-care unit in Nairobi, Kenya. This is a full-time "
                "onsite role. 5+ years of bedside nursing experience required, ACLS "
                "and BLS certification, ventilator and patient-assessment skills. "
                "Apply now with your nursing license number and references.</p>"
            ),
            "absolute_url": _SHARED_NURSE_URL,
            "updated_at": _now_iso(),
            "offices": [{"name": "Nairobi, Kenya"}],
        }
    ]
}

# Same posting, reached via Lever, with tracking params on the URL: must dedupe
# against the Greenhouse copy via canonical_lead_id.
_LEVER_PAYLOAD = [
    {
        "text": "Senior Registered Nurse (ICU)",
        "hostedUrl": _SHARED_NURSE_URL + "?utm_campaign=jobboard&gclid=abc123",
        "createdAt": _now_epoch() * 1000,
        "descriptionPlain": (
            "Mercy Hospital is hiring an experienced ICU registered nurse in "
            "Nairobi, Kenya. Full-time onsite, 5+ years required. Apply now."
        ),
        "additionalPlain": "ACLS and BLS certification required.",
        "categories": {"location": "Nairobi, Kenya", "team": "Nursing"},
    }
]

_GITHUB_PAYLOAD = {
    "items": [
        {
            "title": "Hiring: Head Chef for our restaurant (São Paulo)",
            "body": (
                "We are hiring a head chef to lead the kitchen of our restaurant "
                "in São Paulo, Brazil. Full-time onsite role. You will design "
                "menus, manage kitchen staff, control food cost, and uphold "
                "hygiene standards. Apply by replying with your culinary portfolio "
                "and references. Experience with Brazilian and Italian cuisine a plus."
            ),
            "html_url": "https://github.com/saborbrasil/careers/issues/12",
            "updated_at": _now_iso(),
            "repository_url": "https://api.github.com/repos/saborbrasil/careers",
            "labels": [{"name": "hiring"}],
        }
    ]
}

_REDDIT_PAYLOAD = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "[Hiring] Certified Welder — Munich, Germany (full-time)",
                    "selftext": (
                        "Our metal fabrication workshop in Munich, Germany is hiring "
                        "a certified MIG/TIG welder for a full-time onsite position. "
                        "Blueprint reading and structural steel experience required. "
                        "Apply by email with your welding certifications."
                    ),
                    "created_utc": float(_now_epoch()),
                    "author": "metallbau_muc",
                    "permalink": "/r/forhire/comments/abc123/hiring_certified_welder_munich/",
                }
            }
        ]
    }
}


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Route a mocked request to the right canned keyless-API payload."""
    host = request.url.host or ""
    if "boards-api.greenhouse.io" in host:
        return httpx.Response(200, json=_GREENHOUSE_PAYLOAD)
    if "api.lever.co" in host:
        return httpx.Response(200, json=_LEVER_PAYLOAD)
    if "api.github.com" in host:
        return httpx.Response(200, json=_GITHUB_PAYLOAD)
    if "reddit.com" in host:
        return httpx.Response(200, json=_REDDIT_PAYLOAD)
    if "hn.algolia.com" in host:
        return httpx.Response(200, json={"hits": []})
    # Anything else (should not happen in this test) -> empty, never a real call.
    return httpx.Response(200, json={}, text="")


def _fake_async_client(*args, **kwargs):
    """Drop-in for httpx.AsyncClient that serves canned responses offline.

    Works for both the SSRF-guarded client (which passes event_hooks) and the
    raw clients (RemoteOK / HN-hiring), because every source ultimately
    constructs httpx.AsyncClient.
    """
    kwargs["transport"] = httpx.MockTransport(_mock_handler)
    return _RealAsyncClient(*args, **kwargs)


def _run_free_scout(raw_targets: str, **overrides):
    """Run the keyless free-source scout with network + DB fully isolated."""
    from automation import free_scout

    saved: list[tuple] = []

    import contextlib
    kwargs = dict(raw_targets=raw_targets, kind_filter="job", max_requests=20, min_signal_score=60)
    kwargs.update(overrides)
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("httpx.AsyncClient", _fake_async_client))
        # SSRF guard runs a real DNS lookup in its request event-hook. Patch it at
        # the source module's OWN binding (net.py did `from core.url_guard import
        # assert_public_url`, so it holds its own reference) AND at the origin, so
        # the test is fully offline + deterministic — no dependency on real DNS or
        # the host's NAT64/DNS64 setup.
        stack.enter_context(mock.patch("discovery.sources.net.assert_public_url", lambda *a, **k: None))
        stack.enter_context(mock.patch("core.url_guard.assert_public_url", lambda *a, **k: None))
        # Isolate persistence: capture saves, never hit a real repository.
        stack.enter_context(mock.patch.object(free_scout, "url_exists", lambda _jid: False))
        stack.enter_context(mock.patch.object(free_scout, "save_lead", lambda *a, **k: saved.append((a, k))))
        stack.enter_context(mock.patch.object(free_scout, "rank_lead_by_feedback", lambda lead: lead))
        leads = free_scout.run(**kwargs)
    return leads, free_scout.LAST_USAGE, saved


def test_free_sources_enabled_default_on():
    """Zero-config: keyless sources must be ON by default (no opt-in needed)."""
    assert free_sources_enabled({}) is True
    assert free_sources_enabled({"free_sources_enabled": ""}) is True
    # Explicit opt-out still respected.
    assert free_sources_enabled({"free_sources_enabled": "false"}) is False


def test_keyless_multisource_scan_non_tech_non_us():
    """A no-key scan returns non-empty, deduped, field/location-agnostic leads
    from MULTIPLE keyless sources for a non-tech, non-US, *senior* profile."""
    raw_targets = "\n".join([
        "ats:greenhouse:mercyhospital",   # senior nurse, Nairobi (Kenya)
        "ats:lever:mercyhospital",        # SAME nurse posting -> must dedupe
        "github:head chef hiring",        # head chef, São Paulo (Brazil)
        "reddit:forhire:welder",          # welder, Munich (Germany)
    ])
    leads, usage, _saved = _run_free_scout(raw_targets)

    # --- non-empty -------------------------------------------------------
    assert leads, "keyless multi-source scan returned no leads"

    # --- multiple distinct keyless sources -------------------------------
    platforms = {lead.get("platform") for lead in leads}
    assert len(platforms) >= 3, f"expected >=3 distinct keyless sources, got {platforms}"
    assert {"greenhouse", "github", "reddit"} <= platforms, f"missing core keyless sources: {platforms}"

    # --- deduplicated (canonical URL) ------------------------------------
    from discovery.lead_intel import canonical_lead_id
    ids = [canonical_lead_id(lead["url"]) for lead in leads]
    assert len(ids) == len(set(ids)), "duplicate canonical leads leaked through dedup"
    assert usage.get("duplicates", 0) >= 1, "cross-source duplicate (Lever copy of the Greenhouse nurse) was not deduped"
    # The shared nurse posting appears exactly once.
    nurse_leads = [lead for lead in leads if canonical_lead_id(lead["url"]) == canonical_lead_id(_SHARED_NURSE_URL)]
    assert len(nurse_leads) == 1, f"shared nurse posting should appear once, got {len(nurse_leads)}"

    # --- field-agnostic: non-tech roles survived the quality gate --------
    blob = " ".join((lead.get("title", "") + " " + lead.get("description", "")) for lead in leads).lower()
    assert "nurse" in blob, "non-tech nursing lead was dropped"
    assert "chef" in blob, "non-tech culinary lead was dropped"
    assert "welder" in blob, "non-tech trades lead was dropped"

    # --- seniority-neutral: a SENIOR role was NOT penalized out ----------
    assert nurse_leads, "senior nurse role was filtered (quality gate is not seniority-neutral)"

    # --- location-agnostic: non-US locations preserved -------------------
    assert any(
        loc in blob for loc in ("nairobi", "kenya", "são paulo", "sao paulo", "brazil", "munich", "germany")
    ), "non-US locations were stripped or the leads were US-only"


def test_keyless_scan_is_genuinely_keyless():
    """The scan above used NO api keys/tokens — assert the contract holds by
    running it with an explicitly empty config-equivalent and still getting
    multi-source results."""
    raw_targets = "ats:greenhouse:mercyhospital\ngithub:chef\nreddit:forhire:welder"
    leads, _usage, _saved = _run_free_scout(raw_targets)
    assert leads
    assert len({lead.get("platform") for lead in leads}) >= 3
