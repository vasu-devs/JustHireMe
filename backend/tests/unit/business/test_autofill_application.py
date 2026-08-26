"""scripts/autofill_application.py -- field-classification rules
(label/name/id/placeholder/aria-label -> a known question type), region
detection (India vs. overseas, ambiguous, unknown), value resolution
(never guesses -- unresolvable fields come back as ``None``), and the
Playwright-facing fill dispatch with a MOCKED page object (no real browser).

Never reads the real (gitignored) candidate_answers.json -- every test
builds its own small config dict, same as test_apply_assist.py's inline
``_PROFILE``.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import autofill_application as af  # noqa: E402


_CFG = {
    "identity": {
        "name": "Alex Candidate", "first_name": "Alex", "last_name": "Candidate",
        "email": "alex.candidate@example.test", "phone": "+1 555 010 0000",
        "location": "Gurgaon, India", "city": "Gurgaon", "country": "India",
        "portfolio_url": "https://candidate.example.test", "github_url": "https://github.com/example-candidate",
    },
    "experience_years": "11", "experience_years_text": "11+ years",
    "notice_period": "Immediate / can join immediately",
    "resume_path": "",
    "compensation": {"india": "INR 50-75 LPA", "overseas": "USD 120,000-160,000"},
    "work_authorization": {
        "statement": "Indian citizen; no auth needed for India roles; open to EOR overseas.",
        "india": {"authorized": True, "sponsorship_required": False},
        "overseas": {"authorized": False, "sponsorship_required": True},
    },
    "willing_to_relocate": False, "requires_remote": True,
    "relocation_statement": "Not relocating -- Gurgaon-based, remote only.",
    "remote_statement": "Yes -- remote only, not open to onsite/hybrid.",
    "region_keywords": {
        "india": ["india", "bengaluru", "bangalore", "gurgaon", "mumbai", "hyderabad"],
        "overseas": ["united states", "usa", "san francisco", "united kingdom", "london", "europe"],
    },
    "projects": [
        {"title": "AegisQuery", "pitch": "AegisQuery pitch text.", "fit_tags": ["security", "mcp", "sql", "infrastructure"]},
        {"title": "Dialoft", "pitch": "Dialoft pitch text.", "fit_tags": ["voice", "agents", "telephony"]},
    ],
}

_PROFILE = {"identity": _CFG["identity"]}


def _lead(**over) -> dict:
    base = {"job_id": "j1", "title": "Software Engineer", "company": "Acme", "description": "", "location": ""}
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------

def test_classify_matches_common_label_name_and_placeholder_variants():
    cases = {
        "first name": "first_name", "last name": "last_name",
        "e-mail address": "email", "email": "email",
        "phone number": "phone", "mobile": "phone",
        "linkedin profile url": "linkedin", "github username": "github",
        "portfolio / personal website": "portfolio",
        "resume/cv": "resume_upload", "attach your resume": "resume_upload",
        "cover letter": "cover_letter",
        "current ctc": "current_compensation",
        "expected compensation": "compensation_expected", "salary expectation": "compensation_expected",
        "notice period": "notice_period", "when can you start": "notice_period",
        "years of experience": "experience_years", "total experience": "experience_years",
        "do you require visa sponsorship": "sponsorship_required",
        "are you authorized to work in the us": "work_authorized",
        "are you willing to relocate": "willing_to_relocate",
        "are you open to remote work": "open_to_remote",
        "country of residence": "country",
        "current city": "location",
        "why do you want to work here": "why_company",
        "why are you interested in this role": "why_company",
        "tell us about a relevant project": "project_answer",
        "gender": "eeo", "veteran status": "eeo",
        "i agree to the privacy policy": "consent",
        "country code": "phone_country_code",
    }
    for label, expected in cases.items():
        ctx = af._normalize_context({"label": label})
        assert af._classify(ctx) == expected, f"{label!r} -> expected {expected}, got {af._classify(ctx)!r}"


def test_classify_does_not_mangle_brand_names_with_an_internal_capital():
    # Regression: the camelCase->"word split" step used to run over the
    # WHOLE joined context (label included), so "GitHub"/"LinkedIn" -- an
    # ordinary rendered label, not an attribute name -- got mangled into
    # "Git Hub"/"Linked In" and silently missed their own literal patterns
    # (confirmed on live Lever and GitLab forms). The split must apply only
    # to name/id, never to label/ariaLabel/placeholder text.
    assert af._classify(af._normalize_context({"label": "GitHub URL"})) == "github"
    assert af._classify(af._normalize_context({"label": "LinkedIn Profile"})) == "linkedin"
    assert af._classify(af._normalize_context({"label": "GitHub URL", "name": "urls[GitHub]"})) == "github"


def test_classify_camel_case_attribute_names_are_split_into_words():
    ctx = af._normalize_context({"name": "firstName"})
    assert af._classify(ctx) == "first_name"
    ctx = af._normalize_context({"id": "noticePeriodField"})
    assert af._classify(ctx) == "notice_period"


def test_classify_returns_empty_for_unrecognized_labels():
    ctx = af._normalize_context({"label": "How did you hear about us?"})
    assert af._classify(ctx) == ""


# ---------------------------------------------------------------------------
# Region detection
# ---------------------------------------------------------------------------

def test_detect_region_india_from_explicit_city():
    assert af._detect_region(_lead(description="Location - Mumbai, India office"), _CFG) == "india"


def test_detect_region_overseas_from_explicit_city():
    assert af._detect_region(_lead(description="This role is based in San Francisco, United States"), _CFG) == "overseas"


def test_detect_region_ambiguous_when_both_present_is_left_unknown():
    text = "We have offices in India and the United States; this role is remote"
    assert af._detect_region(_lead(description=text), _CFG) == ""


def test_detect_region_unknown_when_neither_present():
    assert af._detect_region(_lead(description="A great place to work, fully remote"), _CFG) == ""


# ---------------------------------------------------------------------------
# _resolve -- never guesses; region-aware; text vs. yes/no controls differ
# ---------------------------------------------------------------------------

def _resolve(field_key, **over):
    kwargs = dict(context="", control_kind="text", control_type="text", lead=_lead(), cfg=_CFG, profile=_PROFILE, folder=None)
    kwargs.update(over)
    return af._resolve(field_key, **kwargs)


def test_resolve_identity_fields_come_straight_from_config():
    assert _resolve("email")["value"] == "alex.candidate@example.test"
    assert _resolve("phone")["value"] == "+1 555 010 0000"
    assert _resolve("first_name")["value"] == "Alex"
    assert _resolve("portfolio")["value"] == "https://candidate.example.test"


def test_resolve_linkedin_has_no_data_and_is_never_guessed():
    d = _resolve("linkedin")
    assert d["value"] is None
    assert "linkedin" in d["note"].lower()


def test_resolve_linkedin_uses_only_an_explicitly_configured_url():
    cfg = {**_CFG, "identity": {**_CFG["identity"], "linkedin_url": "https://www.linkedin.com/in/example/"}}
    d = af._resolve("linkedin", context="", control_kind="text", control_type="text", lead=_lead(), cfg=cfg, profile=_PROFILE, folder=None)
    assert d["value"] == "https://www.linkedin.com/in/example/"


def test_resolve_compensation_is_region_aware():
    india_lead = _lead(description="Bengaluru, India")
    overseas_lead = _lead(description="London, United Kingdom")
    unknown_lead = _lead(description="remote, planet Earth")
    assert af._resolve("compensation_expected", context="", control_kind="text", control_type="text",
                        lead=india_lead, cfg=_CFG, profile=_PROFILE, folder=None)["value"] == "INR 50-75 LPA"
    assert af._resolve("compensation_expected", context="", control_kind="text", control_type="text",
                        lead=overseas_lead, cfg=_CFG, profile=_PROFILE, folder=None)["value"] == "USD 120,000-160,000"
    d = af._resolve("compensation_expected", context="", control_kind="text", control_type="text",
                     lead=unknown_lead, cfg=_CFG, profile=_PROFILE, folder=None)
    assert d["value"] is None  # never guess an unknown region's band


def test_resolve_current_compensation_always_needs_the_human():
    assert _resolve("current_compensation")["value"] is None


def test_resolve_work_authorization_yes_no_is_region_aware():
    india_lead = _lead(description="Gurgaon, India")
    overseas_lead = _lead(description="San Francisco, United States")
    auth_india = af._resolve("work_authorized", context="authorized to work", control_kind="radio_group",
                              control_type="radio", lead=india_lead, cfg=_CFG, profile=_PROFILE, folder=None)
    auth_overseas = af._resolve("work_authorized", context="authorized to work", control_kind="radio_group",
                                 control_type="radio", lead=overseas_lead, cfg=_CFG, profile=_PROFILE, folder=None)
    assert auth_india["value"] is True
    assert auth_overseas["value"] is False


def test_resolve_work_authorization_text_field_gets_the_full_statement():
    d = _resolve("work_authorized", context="describe your work authorization", control_kind="textarea", control_type="textarea")
    assert "EOR" in d["value"]


def test_resolve_negated_question_flips_the_answer():
    # "unable to work without sponsorship" for an India-based role would
    # normally resolve sponsorship_required=False; the negation ("unable",
    # "without") must flip it rather than silently answering the opposite
    # of what's true.
    india_lead = _lead(description="Gurgaon, India")
    d = af._resolve(
        "sponsorship_required", context="are you unable to work without sponsorship",
        control_kind="radio_group", control_type="radio", lead=india_lead, cfg=_CFG, profile=_PROFILE, folder=None,
    )
    assert d["value"] is True  # flipped from the plain False


def test_resolve_relocation_is_always_no_regardless_of_region():
    assert af._resolve("willing_to_relocate", context="willing to relocate", control_kind="radio_group",
                        control_type="radio", lead=_lead(), cfg=_CFG, profile=_PROFILE, folder=None)["value"] is False


def test_resolve_remote_is_always_yes():
    assert af._resolve("open_to_remote", context="open to remote work", control_kind="radio_group",
                        control_type="radio", lead=_lead(), cfg=_CFG, profile=_PROFILE, folder=None)["value"] is True


def test_resolve_notice_period_skips_a_date_picker_but_fills_free_text():
    assert _resolve("notice_period", control_kind="text", control_type="date")["value"] is None
    assert _resolve("notice_period", control_kind="text", control_type="text")["value"] == "Immediate / can join immediately"


def test_resolve_experience_years_prefers_numeric_form_for_number_inputs():
    assert _resolve("experience_years", control_kind="text", control_type="number")["value"] == "11"
    assert _resolve("experience_years", control_kind="text", control_type="text")["value"] == "11+ years"


def test_resolve_eeo_and_consent_are_always_left_for_the_human():
    assert _resolve("eeo")["value"] is None
    assert _resolve("consent")["value"] is None


def test_resolve_resume_upload_requires_a_file_control_and_an_existing_file(tmp_path):
    # Not a file control at all -- e.g. a "resume URL" text field.
    assert _resolve("resume_upload", control_kind="text")["value"] is None

    # File control but the configured path doesn't exist.
    d = _resolve("resume_upload", control_kind="file")
    assert d["value"] is None
    assert "not found" in d["note"]

    # File control with a real file configured.
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-fake")
    cfg = {**_CFG, "resume_path": str(resume)}
    d = af._resolve("resume_upload", context="", control_kind="file", control_type="file",
                     lead=_lead(), cfg=cfg, profile=_PROFILE, folder=None)
    assert d["value"] == str(resume)


def test_resolve_cover_letter_as_file_upload_is_left_for_the_human():
    d = _resolve("cover_letter", control_kind="file", control_type="file")
    assert d["value"] is None
    assert "file upload" in d["note"]


def test_resolve_why_company_and_cover_letter_reuse_apply_assists_own_packet_reader(tmp_path):
    (tmp_path / "cover_letter.md").write_text("Dear team,\n\nBody paragraph.\n\nSincerely,\nAlex\n", encoding="utf-8")
    (tmp_path / "answers.md").write_text("## Why Acme\nAcme's problem is exactly AegisQuery's domain.\n", encoding="utf-8")
    why = af._resolve("why_company", context="", control_kind="textarea", control_type="textarea",
                       lead=_lead(), cfg=_CFG, profile=_PROFILE, folder=tmp_path)
    assert why["value"] == "Acme's problem is exactly AegisQuery's domain."
    cover = af._resolve("cover_letter", context="", control_kind="textarea", control_type="textarea",
                         lead=_lead(), cfg=_CFG, profile=_PROFILE, folder=tmp_path)
    assert "Body paragraph." in cover["value"]


def test_resolve_unrecognized_field_key_is_left_for_the_human():
    assert _resolve("")["value"] is None


# ---------------------------------------------------------------------------
# Project-pick free-text answer (reuses generation.generators.resume._keywords)
# ---------------------------------------------------------------------------

def test_rank_project_pitch_picks_the_project_matching_the_role():
    security_role = _lead(title="Security Engineer, MCP Infrastructure", description="Build governed MCP tooling with SQL access")
    voice_role = _lead(title="Voice Agents Engineer", description="Build telephony and voice agent systems")
    assert af._rank_project_pitch(security_role, _CFG)[0] == "AegisQuery"
    assert af._rank_project_pitch(voice_role, _CFG)[0] == "Dialoft"


def test_rank_project_pitch_returns_none_without_any_configured_projects():
    assert af._rank_project_pitch(_lead(), {**_CFG, "projects": []}) is None


# ---------------------------------------------------------------------------
# _best_option -- word-boundary safe (e.g. "No" must not match "November")
# ---------------------------------------------------------------------------

def test_best_option_prefers_exact_then_word_boundary_then_substring():
    opts = [{"value": "1", "label": "Yes"}, {"value": "2", "label": "No"}]
    assert af._best_option("Yes", opts)["value"] == "1"
    assert af._best_option("No", opts) is not None
    assert af._best_option("Nope", opts) is None


def test_best_option_word_boundary_does_not_false_match_inside_a_longer_word():
    opts = [{"value": "1", "label": "November intake"}]
    assert af._best_option("No", opts) is None


# ---------------------------------------------------------------------------
# _looks_like_manual_only -- leads that can never be form-filled (an HN
# discussion-thread URL, or raw forum-post text mistaken for a title/
# company), confirmed against the real queue.
# ---------------------------------------------------------------------------

def test_looks_like_manual_only_flags_a_hacker_news_item_url():
    lead = _lead(url="https://news.ycombinator.com/item?id=48766112")
    assert af._looks_like_manual_only(lead) == "manual: email/HN post"


def test_looks_like_manual_only_flags_raw_forum_post_text_in_title_or_company():
    lead = _lead(title="Hiring at We are hiring full-stack and applie", company="We are hiring full-sta")
    assert af._looks_like_manual_only(lead) == "manual: email/HN post"


def test_looks_like_manual_only_leaves_a_real_posting_alone():
    lead = _lead(title="Software Engineer", company="Acme", url="https://jobs.ashbyhq.com/acme/xyz")
    assert af._looks_like_manual_only(lead) == ""


# ---------------------------------------------------------------------------
# Playwright-facing fill dispatch -- MOCKED page/locator, no real browser.
# ---------------------------------------------------------------------------

class _FakeLocator:
    def __init__(self, page, selector):
        self._page = page
        self.selector = selector
        self._checked = False

    @property
    def first(self):
        return self

    def nth(self, i):
        return _FakeLocator(self._page, f"{self.selector}::nth({i})")

    def is_checked(self):
        return self._checked

    def check(self, timeout=None):
        self._checked = True
        self._page.actions.append(("check", self.selector))

    def fill(self, value, timeout=None):
        self._page.actions.append(("fill", self.selector, value))

    def select_option(self, value=None, label=None, timeout=None):
        self._page.actions.append(("select_option", self.selector, value if value is not None else label))

    def set_input_files(self, path, timeout=None):
        self._page.actions.append(("set_input_files", self.selector, path))


class _FakePage:
    def __init__(self):
        self.actions: list[tuple] = []

    def locator(self, selector):
        return _FakeLocator(self, selector)


def test_perform_fill_text_field():
    page = _FakePage()
    ok, note = af._perform_fill(page, {"kind": "text", "selector": "#email"}, "a@b.com")
    assert ok, note
    assert page.actions == [("fill", "#email", "a@b.com")]


def test_perform_fill_checkbox_checks_only_when_true():
    page = _FakePage()
    ok, _ = af._perform_fill(page, {"kind": "checkbox", "selector": "#sponsor"}, True)
    assert ok and page.actions == [("check", "#sponsor")]

    page2 = _FakePage()
    ok2, _ = af._perform_fill(page2, {"kind": "checkbox", "selector": "#sponsor"}, False)
    assert ok2 and page2.actions == []  # left unchecked, no spurious call


def test_perform_fill_select_matches_by_option_text():
    page = _FakePage()
    f = {"kind": "select", "selector": "select#country", "options": [{"value": "IN", "label": "India"}, {"value": "US", "label": "United States"}]}
    ok, _ = af._perform_fill(page, f, "India")
    assert ok
    assert page.actions == [("select_option", "select#country", "IN")]


def test_perform_fill_radio_group_checks_the_matching_yes_no_option():
    page = _FakePage()
    f = {"kind": "radio_group", "name": "authorized", "options": [{"value": "true", "label": "Yes"}, {"value": "false", "label": "No"}]}
    ok, _ = af._perform_fill(page, f, True)
    assert ok
    assert page.actions == [("check", 'input[type="radio"][name="authorized"]::nth(0)')]


def test_perform_fill_radio_group_with_no_matching_option_reports_and_does_not_click():
    page = _FakePage()
    f = {"kind": "radio_group", "name": "authorized", "options": [{"value": "1", "label": "Maybe"}]}
    ok, note = af._perform_fill(page, f, True)
    assert not ok
    assert page.actions == []
    assert "Maybe" in note


def test_perform_fill_file_input():
    page = _FakePage()
    f = {"kind": "file", "selector": "input[type=file]"}
    ok, _ = af._perform_fill(page, f, "/tmp/resume.pdf")
    assert ok
    assert page.actions == [("set_input_files", "input[type=file]", "/tmp/resume.pdf")]


def test_apply_all_needs_human_carries_the_intended_value_when_one_was_resolved():
    # A field that resolves to a real answer but automation still can't
    # apply it (a react-select combobox, or a fill that raises) must surface
    # that answer as something to paste -- not just explain why it's blank.
    # (Fields that are None-by-design, e.g. EEO/consent, correctly carry no
    # "value" -- there is nothing to paste, that's the whole point.)
    page = _FakePage()
    lead = _lead()
    fields = [
        {"kind": "text", "type": "text", "name": "howheard", "id": "", "label": "How did you hear about us?",
         "ariaLabel": "", "placeholder": "", "role": "combobox", "selector": "#howheard", "options": []},
    ]
    # "How did you hear about us?" isn't classified -> value is None -> no
    # "value" key. Force a classified-but-combobox case directly via a field
    # whose label DOES classify (full name) but is rendered as a combobox.
    fields = [
        {"kind": "text", "type": "text", "name": "full_name", "id": "", "label": "Full Name",
         "ariaLabel": "", "placeholder": "", "role": "combobox", "selector": "#full_name", "options": []},
    ]
    _, needs_human = af.apply_all(page, fields, lead, _CFG, _PROFILE, None)
    assert len(needs_human) == 1
    assert needs_human[0]["value"] == "Alex Candidate"


def test_apply_all_needs_human_has_no_value_key_when_nothing_was_resolved():
    page = _FakePage()
    lead = _lead()
    fields = [
        {"kind": "text", "type": "text", "name": "linkedin", "id": "", "label": "LinkedIn URL", "ariaLabel": "",
         "placeholder": "", "selector": "#linkedin", "options": []},
    ]
    _, needs_human = af.apply_all(page, fields, lead, _CFG, _PROFILE, None)
    assert len(needs_human) == 1
    assert "value" not in needs_human[0]


def test_apply_all_splits_scanned_fields_into_filled_and_needs_human(tmp_path):
    page = _FakePage()
    lead = _lead(description="Gurgaon, India")
    fields = [
        {"kind": "text", "type": "text", "name": "first_name", "id": "first_name", "label": "", "ariaLabel": "",
         "placeholder": "First Name", "selector": "#first_name", "options": []},
        {"kind": "text", "type": "text", "name": "linkedin", "id": "", "label": "LinkedIn URL", "ariaLabel": "",
         "placeholder": "", "selector": "#linkedin", "options": []},
        {"kind": "radio_group", "type": "radio", "name": "auth", "id": "", "label": "Are you legally authorized to work in India?",
         "ariaLabel": "", "placeholder": "", "selector": "",
         "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
        {"kind": "text", "type": "text", "name": "howheard", "id": "", "label": "How did you hear about us?",
         "ariaLabel": "", "placeholder": "", "selector": "#howheard", "options": []},
    ]
    filled, needs_human = af.apply_all(page, fields, lead, _CFG, _PROFILE, None)

    filled_labels = {item["label"] for item in filled}
    needs_labels = {item["label"] for item in needs_human}
    assert any("First Name" in lbl for lbl in filled_labels)
    assert any("authorized to work in India" in lbl for lbl in filled_labels)
    assert "LinkedIn URL" in needs_labels
    assert "How did you hear about us?" in needs_labels
    assert ("fill", "#first_name", "Alex") in page.actions


# ---------------------------------------------------------------------------
# Session mode -- `_run_session`'s state machine. Every collaborator that
# would touch a real browser or the real DB (the queue, per-role
# fill/screenshot, the applied-mark, the human prompt) is injected with a
# fake, per `_run_session`'s own contract -- no real Playwright page, no
# real sqlite file, anywhere in this section.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402


def _session_lead(job_id, **over):
    base = {"job_id": job_id, "title": f"Role {job_id}", "company": "Co", "score": 70,
            "url": f"https://example.com/{job_id}", "platform": "greenhouse", "status": "draft_ready"}
    base.update(over)
    return base


def _fake_result(**over):
    base = {"filled": [{"label": "Email", "field": "email", "preview": "a@b.com"}],
            "needs_human": [], "gated_hint": "", "screenshot_path": None}
    base.update(over)
    return base


def _scripted(*choices):
    """A fake `prompt` -- returns each of `choices` in order, one per call."""
    it = iter(choices)
    return lambda: next(it)


def _run(leads, prompts, *, limit=None, visit_role=None, mark_applied=None):
    """`_run_session` wired with fakes: an in-memory queue (filtered by
    `_run_session`'s own `seen` tracking, exactly like the real
    apply_assist._queue would be after a status change), a scripted prompt,
    and trackers for which job_ids were visited/marked so tests can assert
    on them directly."""
    visited: list[str] = []
    marked: list[str] = []

    def default_visit(lead):
        visited.append(lead["job_id"])
        return _fake_result()

    def default_mark(job_id):
        marked.append(job_id)
        return 0

    result = af._run_session(
        page=None, cfg=_CFG, profile=_PROFILE, db_path="unused-in-tests", args=SimpleNamespace(limit=limit),
        queue_fn=lambda: leads,
        visit_role=visit_role or default_visit,
        mark_applied=mark_applied or default_mark,
        prompt=_scripted(*prompts),
    )
    return result, visited, marked


def test_run_session_enter_marks_applied_and_advances_in_the_same_context():
    leads = [_session_lead("j1"), _session_lead("j2")]
    result, visited, marked = _run(leads, prompts=["enter", "enter"])
    assert result == {"submitted": 2, "skipped": 0, "remaining": 0}
    assert visited == ["j1", "j2"]  # same in-memory session, both roles loaded in order
    assert marked == ["j1", "j2"]


def test_run_session_skip_marks_nothing_and_still_advances():
    # The core invariant: pressing [s] on every role must leave `marked`
    # completely empty while still moving through the whole queue.
    leads = [_session_lead("j1"), _session_lead("j2")]
    result, visited, marked = _run(leads, prompts=["s", "s"])
    assert result == {"submitted": 0, "skipped": 2, "remaining": 0}
    assert visited == ["j1", "j2"]
    assert marked == []  # <- nothing marked, ever, on skip


def test_run_session_quit_stops_immediately_without_marking_or_skipping():
    leads = [_session_lead("j1"), _session_lead("j2")]
    result, visited, marked = _run(leads, prompts=["q"])
    assert result == {"submitted": 0, "skipped": 0, "remaining": 2}
    assert visited == ["j1"]  # only the first role was ever loaded
    assert marked == []


def test_run_session_quit_after_some_progress_leaves_the_rest_queued():
    leads = [_session_lead("j1"), _session_lead("j2"), _session_lead("j3")]
    result, visited, marked = _run(leads, prompts=["enter", "s", "q"])
    assert result == {"submitted": 1, "skipped": 1, "remaining": 1}
    assert visited == ["j1", "j2", "j3"]
    assert marked == ["j1"]


def test_run_session_limit_stops_after_n_processed_roles():
    leads = [_session_lead("j1"), _session_lead("j2"), _session_lead("j3")]
    result, visited, _marked = _run(leads, prompts=["enter"], limit=1)
    assert result == {"submitted": 1, "skipped": 0, "remaining": 2}
    assert visited == ["j1"]  # loop stopped before even loading j2


def test_run_session_failed_mark_is_not_counted_as_submitted_but_still_advances():
    # mark_applied returning non-zero (an illegal transition, a DB error --
    # anything review.cmd_mark itself rejected) must never be silently
    # treated as a success, but the session still has to move on rather than
    # getting stuck re-prompting the same role forever.
    leads = [_session_lead("j1"), _session_lead("j2")]
    result, visited, _marked = _run(leads, prompts=["enter", "enter"], mark_applied=lambda job_id: 2)
    assert result == {"submitted": 0, "skipped": 2, "remaining": 0}
    assert visited == ["j1", "j2"]


def test_run_session_skips_a_role_with_no_apply_url_without_prompting():
    leads = [_session_lead("j1", url=""), _session_lead("j2")]
    result, visited, _marked = _run(leads, prompts=["enter"])  # only ONE prompt needed -- j1 is auto-skipped
    assert result == {"submitted": 1, "skipped": 0, "remaining": 0}
    assert visited == ["j2"]  # j1 never reached visit_role at all


def test_run_session_skips_a_blocked_url_without_prompting():
    # A real (not injected) call to assert_public_url -- a loopback literal
    # needs no DNS and is deterministic offline.
    leads = [_session_lead("j1", url="http://127.0.0.1/apply"), _session_lead("j2")]
    result, visited, _marked = _run(leads, prompts=["enter"])
    assert result == {"submitted": 1, "skipped": 0, "remaining": 0}
    assert visited == ["j2"]


def test_run_session_skips_an_hn_item_url_lead_without_prompting():
    # An HN "who's hiring" thread stored as the apply URL has no form to
    # fill, ever -- confirmed against the real queue (news.ycombinator.com/
    # item links with no company ATS behind them).
    leads = [_session_lead("j1", url="https://news.ycombinator.com/item?id=48766112"), _session_lead("j2")]
    result, visited, _marked = _run(leads, prompts=["enter"])
    assert result == {"submitted": 1, "skipped": 0, "remaining": 0}
    assert visited == ["j2"]  # j1 never reached visit_role -- no browser tab opened for it


def test_run_session_skips_a_lead_with_raw_forum_post_text_as_title_and_company():
    # Real example from the queue: the scraper truncated one HN comment into
    # both the title and company fields.
    leads = [
        _session_lead("j1", title="Hiring at We are hiring full-stack and applie",
                       company="We are hiring full-sta", url="https://example.com/careers/1"),
        _session_lead("j2"),
    ]
    result, visited, _marked = _run(leads, prompts=["enter"])
    assert result == {"submitted": 1, "skipped": 0, "remaining": 0}
    assert visited == ["j2"]


def test_run_session_a_visit_role_exception_skips_without_marking_and_does_not_crash():
    leads = [_session_lead("j1"), _session_lead("j2")]

    def flaky_visit(lead):
        if lead["job_id"] == "j1":
            raise RuntimeError("page crashed")
        return _fake_result()

    result, _visited, marked = _run(leads, prompts=["enter"], visit_role=flaky_visit)
    assert result == {"submitted": 1, "skipped": 0, "remaining": 0}
    assert marked == ["j2"]  # j1's crash never reached mark_applied


def test_run_session_empty_queue_returns_a_clean_zero_summary():
    result, visited, _marked = _run([], prompts=[])
    assert result == {"submitted": 0, "skipped": 0, "remaining": 0}
    assert visited == []


def test_prompt_session_choice_parses_enter_skip_quit(monkeypatch):
    for raw, expected in [("", "enter"), ("  ", "enter"), ("s", "s"), ("S", "s"), ("skip", "s"),
                           ("q", "q"), ("Q", "q"), ("quit", "q"), ("anything else", "enter")]:
        monkeypatch.setattr("builtins.input", lambda _prompt, _raw=raw: _raw)
        assert af._prompt_session_choice() == expected


def test_mark_applied_chains_draft_ready_through_approved_then_calls_review_cmd_mark(monkeypatch):
    # Delegates entirely to apply_assist.review.cmd_mark -- this must NOT
    # reimplement review.TRANSITIONS/outcome_feedback_for itself.
    calls = []

    def fake_cmd_mark(ns):
        calls.append(ns.new_status)
        return 0

    monkeypatch.setattr(af.apply_assist.review, "cmd_mark", fake_cmd_mark)
    monkeypatch.setattr(af, "get_lead_by_id", lambda job_id, db_path: {"status": "draft_ready"})
    args = SimpleNamespace(db=None, drafts_dir="drafts", profile="profile.json")

    rc = af._mark_applied("j1", "unused-in-tests", args)
    assert rc == 0
    assert calls == ["approved", "applied"]  # chained, both via review.cmd_mark


def test_mark_applied_skips_the_approved_step_when_already_approved(monkeypatch):
    calls = []
    monkeypatch.setattr(af.apply_assist.review, "cmd_mark", lambda ns: calls.append(ns.new_status) or 0)
    monkeypatch.setattr(af, "get_lead_by_id", lambda job_id, db_path: {"status": "approved"})
    args = SimpleNamespace(db=None, drafts_dir="drafts", profile="profile.json")

    af._mark_applied("j1", "unused-in-tests", args)
    assert calls == ["applied"]  # no redundant approved-transition call


def test_mark_applied_stops_and_propagates_the_error_if_the_approved_step_fails(monkeypatch):
    monkeypatch.setattr(af.apply_assist.review, "cmd_mark", lambda ns: 2)  # simulate an illegal transition
    monkeypatch.setattr(af, "get_lead_by_id", lambda job_id, db_path: {"status": "draft_ready"})
    args = SimpleNamespace(db=None, drafts_dir="drafts", profile="profile.json")

    rc = af._mark_applied("j1", "unused-in-tests", args)
    assert rc == 2


# ---------------------------------------------------------------------------
# Strict batch mode -- an explicit separate flow. These tests cover the
# submission gate/state machine without opening Playwright or an ATS.
# ---------------------------------------------------------------------------

class _GatePage:
    def __init__(self, *, captcha=False, controls=None):
        self.captcha = captcha
        self.controls = controls if controls is not None else []

    def evaluate(self, script):
        if script == af._CAPTCHA_PRESENT_JS:
            return self.captcha
        if script == af._FINAL_SUBMIT_CONTROLS_JS:
            return self.controls
        raise AssertionError("unexpected page script")


def test_submission_gate_requires_zero_unresolved_fields_no_captcha_and_one_final_control():
    result = _fake_result()
    page = _GatePage(controls=[{"label": "Submit application", "selector": "button[type=submit]"}])
    assert af._submission_gate(page, result) == (True, "")

    assert af._submission_gate(_GatePage(captcha=True, controls=page.controls), result) == (False, "CAPTCHA detected")
    assert af._submission_gate(page, _fake_result(needs_human=[{"label": "Work authorization"}]))[0] is False
    assert af._submission_gate(_GatePage(controls=[]), result)[0] is False
    assert af._submission_gate(_GatePage(controls=page.controls * 2), result)[0] is False


def test_batch_mode_ignores_unrecognized_optional_fields_but_never_required_ones():
    page = _FakePage()
    optional = {
        "kind": "text", "type": "text", "name": "referral", "id": "", "label": "How did you hear about us?",
        "ariaLabel": "", "placeholder": "", "selector": "#referral", "options": [], "required": False,
    }
    required = {**optional, "required": True}
    _, optional_needs_human = af.apply_all(page, [optional], _lead(), _CFG, _PROFILE, None, auto_submit=True)
    _, required_needs_human = af.apply_all(page, [required], _lead(), _CFG, _PROFILE, None, auto_submit=True)
    assert optional_needs_human == []
    assert len(required_needs_human) == 1


def test_batch_mode_may_check_only_a_plain_privacy_checkbox_when_explicitly_enabled():
    field = {
        "kind": "checkbox", "type": "checkbox", "name": "privacy", "id": "privacy", "label": "I agree to the privacy policy",
        "optionLabel": "I agree to the privacy policy", "ariaLabel": "", "placeholder": "", "selector": "#privacy", "options": [], "required": True,
    }
    page = _FakePage()
    filled, needs_human = af.apply_all(
        page, [field], _lead(), _CFG, _PROFILE, None, auto_submit=True, allow_privacy_consent=True,
    )
    assert needs_human == []
    assert filled[0]["field"] == "consent"
    assert ("check", "#privacy") in page.actions


def _run_batch(leads, outcomes, *, limit=None, mark_result=0):
    visited, marked, events = [], [], []
    outcome_iter = iter(outcomes)
    result = af._run_batch(
        page=None, cfg=_CFG, profile=_PROFILE, db_path="unused-in-tests", args=SimpleNamespace(limit=limit, pause_for_captcha=True),
        queue_fn=lambda: leads,
        visit_role=lambda lead: visited.append(lead["job_id"]) or _fake_result(),
        submit=lambda _result: next(outcome_iter),
        mark_applied=lambda job_id: marked.append(job_id) or mark_result,
        event_fn=lambda job_id, event: events.append((job_id, event)),
        captcha_prompt=lambda: None,
    )
    return result, visited, marked, events


def test_run_batch_marks_only_confirmed_submissions_and_continues_after_safe_skips():
    leads = [_session_lead("j1"), _session_lead("j2"), _session_lead("j3")]
    outcomes = [
        {"status": "skipped", "reason": "1 required field remains unresolved"},
        {"status": "submitted", "reason": "application confirmation detected"},
        {"status": "submitted", "reason": "application confirmation detected"},
    ]
    result, visited, marked, events = _run_batch(leads, outcomes)
    assert result == {"submitted": 2, "skipped": 1, "needs_review": 0, "remaining": 0}
    assert visited == ["j1", "j2", "j3"]
    assert marked == ["j2", "j3"]
    assert events == []


def test_run_batch_pauses_for_a_manual_captcha_then_rechecks_the_same_form():
    prompts = []
    outcomes = iter([
        {"status": "skipped", "reason": "CAPTCHA detected"},
        {"status": "submitted", "reason": "application confirmation detected"},
    ])
    marked = []
    result = af._run_batch(
        page=None, cfg=_CFG, profile=_PROFILE, db_path="unused-in-tests", args=SimpleNamespace(limit=None, pause_for_captcha=True),
        queue_fn=lambda: [_session_lead("j1")],
        visit_role=lambda _lead: _fake_result(),
        submit=lambda _result: next(outcomes),
        mark_applied=lambda job_id: marked.append(job_id) or 0,
        captcha_prompt=lambda: prompts.append("solved"),
    )
    assert prompts == ["solved"]
    assert marked == ["j1"]
    assert result == {"submitted": 1, "skipped": 0, "needs_review": 0, "remaining": 0}


def test_run_batch_stops_on_an_uncertain_click_to_prevent_a_duplicate_retry():
    leads = [_session_lead("j1"), _session_lead("j2")]
    result, visited, marked, events = _run_batch(
        leads, [{"status": "uncertain", "reason": "no confirmation page"}],
    )
    assert result == {"submitted": 0, "skipped": 0, "needs_review": 1, "remaining": 2}
    assert visited == ["j1"]
    assert marked == []
    assert events == [("j1", "application_submission_uncertain")]


def test_run_batch_stops_when_crm_marking_fails_after_a_confirmed_external_submit():
    result, visited, marked, events = _run_batch(
        [_session_lead("j1"), _session_lead("j2")],
        [{"status": "submitted", "reason": "application confirmation detected"}], mark_result=2,
    )
    assert result == {"submitted": 0, "skipped": 0, "needs_review": 1, "remaining": 2}
    assert visited == ["j1"]
    assert marked == ["j1"]
    assert events == [("j1", "application_submitted_crm_mark_failed")]


def test_tab_batch_keeps_a_captcha_blocker_open_and_closes_a_confirmed_submission(monkeypatch):
    monkeypatch.setattr(af, "assert_public_url", lambda _url: None)
    blocker_page, submitted_page = object(), object()
    pages = [blocker_page, submitted_page]
    closed = []
    marked = []
    outcomes = iter([
        {"status": "skipped", "reason": "CAPTCHA detected"},
        {"status": "submitted", "reason": "application confirmation detected"},
    ])
    result, blockers = af._run_tab_batch(
        browser_ctx=None, cfg=_CFG, profile=_PROFILE, db_path="unused-in-tests",
        args=SimpleNamespace(limit=None, inter_application_delay=0),
        queue_fn=lambda: [_session_lead("j1"), _session_lead("j2")],
        page_factory=lambda: pages.pop(0),
        close_page=lambda page: closed.append(page),
        wait_between=lambda _page: None,
        visit_role=lambda _page, _lead: _fake_result(),
        submit=lambda _page, _result: next(outcomes),
        mark_applied=lambda job_id: marked.append(job_id) or 0,
    )
    assert result == {"submitted": 1, "skipped": 0, "needs_review": 1, "remaining": 0}
    assert marked == ["j2"]
    assert len(blockers) == 1
    assert blockers[0]["lead"]["job_id"] == "j1"
    assert closed == [submitted_page]  # only the submitted role was closed


# ---------------------------------------------------------------------------
# Reveal-vs-submit predicate (Ashby's "Apply for this Job" et al.) --
# `_find_reveal_control`/`_click_reveal_control` against a MOCKED page here,
# proving the PYTHON-side contract: a reported candidate is clicked exactly
# once, and a click that unexpectedly lands on a confirmation page aborts
# loudly instead of being swallowed. The actual in-browser JS predicate that
# decides reveal-vs-submit in the first place (`_REVEAL_CANDIDATES_JS` --
# vocabulary + the <form>-membership check) is proven separately below
# against a REAL headless Chromium (opt-in, JHM_LIVE_BROWSER=1), since no
# DOM/JS engine runs in this file's plain mocked-page tests.
# ---------------------------------------------------------------------------

class _RevealLocator:
    def __init__(self, page, selector):
        self._page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._page.clicks.append(self.selector)


class _RevealPage:
    def __init__(self, *, candidates=None, confirmed_after_click=False, url="https://jobs.ashbyhq.com/acme/xyz"):
        self._candidates = candidates if candidates is not None else []
        self._confirmed_after_click = confirmed_after_click
        self.url = url
        self.clicks: list[str] = []

    def evaluate(self, script):
        if script == af._REVEAL_CANDIDATES_JS:
            return self._candidates
        if script == af._SUBMISSION_CONFIRMED_JS:
            return self._confirmed_after_click
        raise AssertionError("unexpected page script")

    def locator(self, selector):
        return _RevealLocator(self, selector)

    def wait_for_timeout(self, ms):
        pass


def test_find_reveal_control_returns_the_disclosed_candidate_the_page_reports():
    # REVEAL ALLOWED direction: the in-page JS found exactly the kind of
    # control Ashby uses ("Apply for this Job") -- _find_reveal_control just
    # surfaces it, it's the caller (_fill_role) that only ever calls this
    # when zero fields are on the page yet.
    page = _RevealPage(candidates=[{"label": "Apply for this Job"}])
    assert af._find_reveal_control(page) == {"label": "Apply for this Job"}


def test_find_reveal_control_returns_none_when_nothing_is_revealable():
    # SUBMIT REFUSED direction, from this function's own contract: this is
    # exactly what the real JS predicate returns for a page whose only
    # apply-vocabulary control is a submit button (inside a <form>, or
    # literally labelled Submit/Send/Finish/...) -- see the live DOM test
    # below for the actual browser-side exclusion. An empty report and "safe
    # to click nothing" are the same thing here.
    assert af._find_reveal_control(_RevealPage(candidates=[])) is None


def test_click_reveal_control_clicks_the_marked_element_exactly_once():
    page = _RevealPage(candidates=[{"label": "Apply for this Job"}])
    af._click_reveal_control(page, {"label": "Apply for this Job"})
    assert page.clicks == ['[data-jhm-reveal-candidate="0"]']


def test_click_reveal_control_aborts_loudly_on_an_unexpected_confirmation_page():
    # Safety trip-wire: if a "reveal" click somehow lands on a
    # thank-you/confirmation page, this must raise -- never silently report
    # "still no form here" -- so the caller's existing exception handling
    # (session/batch's per-lead try/except) surfaces it and skips the lead.
    page = _RevealPage(candidates=[{"label": "Apply for this Job"}], confirmed_after_click=True)
    with pytest.raises(RuntimeError, match="submission-confirmation"):
        af._click_reveal_control(page, {"label": "Apply for this Job"})
    assert page.clicks == ['[data-jhm-reveal-candidate="0"]']  # still only ever clicked once


_LIVE_BROWSER = os.environ.get("JHM_LIVE_BROWSER", "").strip().lower() in {"1", "true", "yes", "on"}
_live_browser_only = pytest.mark.skipif(
    not _LIVE_BROWSER, reason="opt-in real-browser test: set JHM_LIVE_BROWSER=1 (needs Playwright Chromium)",
)

# Ashby's real "Apply for this Job" -- NOT inside a <form>, zero fields on
# the page yet. This is the exact shape the over-restriction used to refuse.
_ASHBY_STYLE_GATED_PAGE = """
<!doctype html><html><body>
  <h1>Tech Lead Manager @ Acme</h1>
  <p>role description text...</p>
  <button type="button">Apply for this Job</button>
</body></html>
"""

# An already-filled form whose own submit control uses the forbidden
# vocabulary from the task spec (Submit/Submit application/Send
# application/Send/Finish/Complete application) -- every one of these must
# be refused, both by label AND by <form> membership.
_FILLED_FORM_WITH_SUBMIT_PAGE = """
<!doctype html><html><body>
  <form>
    <input type="text" name="name" value="Alex Candidate">
    <button type="submit">{label}</button>
  </form>
</body></html>
"""


@_live_browser_only
def test_live_reveal_js_finds_ashbys_apply_for_this_job_button():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_ASHBY_STYLE_GATED_PAGE, wait_until="domcontentloaded")
            candidates = page.evaluate(af._REVEAL_CANDIDATES_JS)
        finally:
            browser.close()
    assert [c["label"] for c in candidates] == ["Apply for this Job"]


@pytest.mark.parametrize("label", ["Submit", "Submit Application", "Send Application", "Send", "Finish", "Complete Application"])
@_live_browser_only
def test_live_reveal_js_refuses_every_forbidden_submit_label_inside_a_filled_form(label):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_FILLED_FORM_WITH_SUBMIT_PAGE.format(label=label), wait_until="domcontentloaded")
            candidates = page.evaluate(af._REVEAL_CANDIDATES_JS)
        finally:
            browser.close()
    assert candidates == [], f"{label!r} must never be treated as a reveal control"


@_live_browser_only
def test_live_final_submit_js_still_finds_those_same_controls_unaffected_by_the_reveal_predicate():
    # Cross-check: the batch-mode submit-detector (_FINAL_SUBMIT_CONTROLS_JS,
    # untouched by this change) still recognizes the real submit control --
    # proving the fix didn't make submit controls invisible to batch mode,
    # it only ever ADDED a separate, narrower reveal path.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_FILLED_FORM_WITH_SUBMIT_PAGE.format(label="Submit Application"), wait_until="domcontentloaded")
            controls = page.evaluate(af._FINAL_SUBMIT_CONTROLS_JS)
        finally:
            browser.close()
    assert [c["label"] for c in controls] == ["Submit Application"]
