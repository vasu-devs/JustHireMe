"""Round-10 audit fixes: tech-name punctuation must not collapse distinct skills
(C / C++ / C#) in deletion identity or import dedup; a partial identity PUT must
not wipe untouched fields."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import mock

from core.types import IdentityBody
from data.graph.profile_base import _norm_key as _graph_norm_key
from data.graph.profile_deletions import _delete_tokens
from profile.service import _dedupe_dict_items, _dedupe_text_items, _norm_key_strict


# --- the punctuation-preserving keys must keep C / C++ / C# distinct ---------------

def test_norm_key_distinguishes_c_family():
    for norm in (_graph_norm_key, _norm_key_strict):
        keys = {norm("C"), norm("C++"), norm("C#")}
        assert len(keys) == 3, (norm, keys)
    # .NET vs NET, Node.js vs Nodejs stay distinct too.
    assert _graph_norm_key(".NET") != _graph_norm_key("NET")
    assert _norm_key_strict("Node.js") != _norm_key_strict("Nodejs")


# --- graph deletion identity: deleting "C" must not tombstone "C++"/"C#" -----------

def test_delete_tokens_do_not_collide_across_c_family():
    assert not (_delete_tokens("skills", "C") & _delete_tokens("skills", "C++")), "deleting C would tombstone C++"
    assert not (_delete_tokens("skills", "C") & _delete_tokens("skills", "C#")), "deleting C would tombstone C#"
    assert not (_delete_tokens("skills", "C++") & _delete_tokens("skills", "C#"))
    # An exact match still deletes itself.
    assert _delete_tokens("skills", "C++") & _delete_tokens("skills", "C++")


def test_free_text_delete_tokens_do_not_collide_on_punctuation():
    # Round-11: free-text credentials differing only by whitespace/colon/comma are
    # DISTINCT graph nodes (_entry_key), so their deletion tombstones must not collide
    # — deleting one must not hide/purge the other.
    a = "AWS Certified: Solutions Architect"
    b = "AWS Certified Solutions Architect"
    assert not (_delete_tokens("certifications", a) & _delete_tokens("certifications", b))
    assert not (_delete_tokens("education", "BSc, Physics") & _delete_tokens("education", "BSc Physics"))
    # Exact match still self-deletes.
    assert _delete_tokens("certifications", a) & _delete_tokens("certifications", a)


# --- import dedup must keep C / C++ / C# as separate skills ------------------------

def test_dedupe_dict_items_keeps_distinct_c_family_skills():
    # Skills are dict items -> _dedupe_dict_items (strict key), so C/C++/C# survive.
    dict_items = [{"n": "C", "id": "1"}, {"n": "C++", "id": "2"}, {"n": "C#", "id": "3"}]
    kept = _dedupe_dict_items(dict_items, "id")
    assert [item["n"] for item in kept] == ["C", "C++", "C#"], kept


def test_dedupe_text_items_still_merges_punctuation_variants():
    # Free-text items (education/certs) keep the lossy key so punctuation/spacing
    # variants of the SAME entry still collapse.
    variants = ["B.Tech - IIT Delhi, 2020", "B.Tech  -  IIT Delhi 2020"]
    assert len(_dedupe_text_items(variants)) == 1


# --- a partial identity PUT dumps only the fields the client actually sent ---------

def test_identity_body_partial_update_excludes_unset():
    # The router uses model_dump(exclude_unset=True); "Add Context" sends only a
    # phone, so only phone reaches update_identity (which merges by `if key in
    # identity`), leaving previously-saved email/linkedin/etc. untouched.
    body = IdentityBody(phone="+1-555-0100")
    assert body.model_dump(exclude_unset=True) == {"phone": "+1-555-0100"}
    # A full edit still carries every field (so intentional clears keep working).
    full = IdentityBody(email="", phone="+1-555-0100", linkedin_url="", github_url="", website_url="", city="")
    assert set(full.model_dump(exclude_unset=True).keys()) == {
        "email", "phone", "linkedin_url", "github_url", "website_url", "city"
    }


# --- manual /fire enriches the lead with identity (not the bare metadata row) ------

def test_actuate_job_enriches_lead_via_get_lead_for_fire():
    from api.routers import automation

    calls: list = []

    class FakeService:
        async def get_lead_for_fire(self, job_id):
            calls.append(("enriched", job_id))
            return {"job_id": job_id, "url": "https://x/apply", "email": "cand@example.com"}, "resume.pdf"

        async def submit_application(self, lead, asset):
            calls.append(("submit", lead.get("email"), asset))
            return True

    class FakeManager:
        async def broadcast(self, *a, **k):
            return None

    def _boom(_job_id):
        raise AssertionError("must not use the bare get_lead_by_id (no identity fields)")

    repo = SimpleNamespace(leads=SimpleNamespace(get_lead_by_id=_boom, mark_applied=lambda job_id: None))
    job_store = SimpleNamespace(create=lambda *a, **k: SimpleNamespace(job_id="j1"), update=lambda *a, **k: None)

    with mock.patch.object(automation, "fire_blocker", return_value=("ok", "")):
        asyncio.run(automation.actuate_job("job-9", FakeManager(), repo=repo, service=FakeService(), job_store=job_store))

    assert ("enriched", "job-9") in calls
    # The enriched lead (carrying email) is what reaches the actuator.
    assert any(c[0] == "submit" and c[1] == "cand@example.com" for c in calls), calls
