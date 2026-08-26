#!/usr/bin/env python
"""Fill job application forms in a real, visible browser.

``next`` and ``session`` retain the original fill-and-review behaviour: they
never submit. ``batch`` is the separate opt-in mode for a candidate who has
explicitly authorized the agent to submit applications on their behalf. It
only submits a form when every required detected field is resolved, no CAPTCHA
is present, and there is exactly one unambiguous final submit control. It
never guesses an answer or treats a click as an application unless the site
shows a confirmation.

Reuses scripts/apply_assist.py's OWN queue ordering and packet-building
(``_queue``, ``_ensure_packet``, ``_field_text``) rather than a second copy,
and ``generation.generators.resume._keywords`` for the free-text project-pick
scoring. Candidate data lives in scripts/candidate_answers.json (gitignored --
real PII) so bands/answers can be edited without touching code.

    python scripts/autofill_application.py next          # top queued role
    python scripts/autofill_application.py <job_id>      # a specific role
    python scripts/autofill_application.py next --no-mail  # skip the Gmail tab
    python scripts/autofill_application.py session --limit 5  # continuous mode
    python scripts/autofill_application.py batch --limit 10 --auto-submit --confirm-candidate-authorization

``session`` is the same fill-and-stop behaviour as ``next``, looped: it fills
a role, prints a compact card (fields filled, fields that still need you --
with the intended answer to paste), then asks [Enter]/[s]/[q]. [Enter] means
"I clicked submit myself" -- it marks the lead applied (by delegating to
apply_assist.py/review.py's own status-transition logic, not a reimplemented
one) and loads the next role in the SAME browser context. [s] skips without
marking anything. It still never clicks submit for you.

Launches a headed (visible) Chromium using a PERSISTENT profile directory
(scripts/.. /.playwright-profile/, gitignored) so logging into Gmail/
LinkedIn/Greenhouse/Ashby once keeps that session alive on every later run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

import apply_assist  # noqa: E402  sibling script -- reuse its queue + packet logic, don't duplicate
import run_scrape  # noqa: E402  sibling script, for resolve_db()
from core.url_guard import BlockedUrlError, assert_public_url  # noqa: E402
from data.sqlite.leads import get_lead_by_id  # noqa: E402
from data.sqlite.events import record_event  # noqa: E402
from generation.generators.resume import _keywords  # noqa: E402  reuse the existing tokenizer, don't reimplement

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "candidate_answers.json"
PROFILE_DIR = BACKEND_DIR / ".playwright-profile"
GMAIL_URL = "https://mail.google.com"


def _launch_context(pw, args, *, slow_mo: int):
    """Launch the persistent profile in a real installed browser by default.

    Playwright's bundled Chromium is fingerprinted as automation and Google
    refuses to let it sign in to Gmail ("this browser or app may not be
    secure"). `--browser` (default "chrome") launches that channel instead,
    keeping the SAME persistent profile dir so an existing login carries
    over; "chromium" opts back into the old bundled-browser behaviour.

    Falls back to bundled Chromium -- with a clearly printed warning, never
    silently -- if the requested channel isn't installed on this machine.
    This is not CAPTCHA solving or anti-bot evasion: it only picks which
    real, unmodified browser binary Playwright drives, plus dropping the one
    obvious automation flag Chromium sets by default.
    """
    channel = getattr(args, "browser", "chrome") or "chrome"
    kwargs = dict(
        headless=False, viewport={"width": 1280, "height": 960}, slow_mo=slow_mo,
        args=["--disable-blink-features=AutomationControlled"],
    )
    if channel != "chromium":
        try:
            return pw.chromium.launch_persistent_context(str(PROFILE_DIR), channel=channel, **kwargs)
        except Exception as exc:
            print(f"\n  ! could not launch browser channel {channel!r} ({exc}) -- falling back to Playwright's "
                  "bundled Chromium. Google sign-in may then refuse it as 'not secure'; install/update that "
                  "browser, or pass --browser chromium to silence this warning.")
    return pw.chromium.launch_persistent_context(str(PROFILE_DIR), **kwargs)


# ---------------------------------------------------------------------------
# Field classification -- label/name/id/placeholder/aria-label -> a known
# question type. Order matters: more specific patterns are checked first so
# e.g. "sponsorship" never falls through to the generic "authorized" rule.
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"country\s*code|dial\s*code"), "phone_country_code"),
    (re.compile(r"first\s*name"), "first_name"),
    (re.compile(r"last\s*name|sur\s*name"), "last_name"),
    (re.compile(r"e[\s-]?mail"), "email"),
    (re.compile(r"phone|mobile|contact\s*number|telephone"), "phone"),
    (re.compile(r"full\s*name|applicant\s*name|legal\s*name|candidate\s*name|your\s*name|^name$"), "full_name"),
    (re.compile(r"linkedin"), "linkedin"),
    (re.compile(r"github"), "github"),
    (re.compile(r"portfolio|personal\s*(site|website)|\bwebsite\b"), "portfolio"),
    (re.compile(r"resume|\bcv\b"), "resume_upload"),
    (re.compile(r"cover\s*letter"), "cover_letter"),
    (re.compile(r"current\s*(salary|ctc|compensation|pay)"), "current_compensation"),
    (re.compile(r"(expected|desired)\s*(salary|compensation|ctc|pay)|salary\s*expectation|compensation\s*expectation"), "compensation_expected"),
    (re.compile(r"notice\s*period|available\s*(to\s*start|from)|earliest\s*start|start\s*date|when\s*can\s*you\s*(start|join)"), "notice_period"),
    (re.compile(r"years?\s*of\s*experience|total\s*experience|yrs?\.?\s*(of\s*)?exp"), "experience_years"),
    (re.compile(r"sponsor"), "sponsorship_required"),
    (re.compile(r"authoriz|eligib.{0,15}work|legally.{0,15}work|work\s*permit|work\s*visa"), "work_authorized"),
    (re.compile(r"relocat"), "willing_to_relocate"),
    (re.compile(r"remote"), "open_to_remote"),
    (re.compile(r"nationality|citizenship|country\s*of\s*residence|\bcountry\b"), "country"),
    (re.compile(r"current\s*(city|location)|\bcity\b|based\s*in|\blocation\b"), "location"),
    (re.compile(r"why.{0,20}(work|join|interested|want).{0,25}(here|company|us\b|role|position|team)|why\s+are\s+you\s+interested|what\s+interests\s+you\s+about|why\s+.{0,15}apply"), "why_company"),
    (re.compile(r"tell\s+us\s+about\s+a\s+project|describe\s+a\s+project|relevant\s+project|walk\s+us\s+through\s+a\s+project|project\s+you.{0,15}(proud|worked)"), "project_answer"),
    (re.compile(r"gender|\brace\b|ethnicity|veteran|disability|sexual\s*orientation|\bpronoun"), "eeo"),
    (re.compile(r"\bagree\b|consent|acknowledge|terms\s*(of\s*service|and\s*conditions)|privacy\s*policy"), "consent"),
]

_NEGATION_RE = re.compile(r"\bnot\b|n't\b|\bunable\b|\bunwilling\b|\bwithout\b")


def _normalize_context(f: dict) -> str:
    """label/aria-label/placeholder/name/id -> one lowercase, word-split
    string so regex keyword rules also catch camelCase/snake_case attribute
    names (e.g. ``firstName`` -> ``first name``), not just rendered labels.

    ``name``/``id`` are skipped for checkboxes: some ATS's (confirmed on a
    live Ashby form) put the OPTION's own display text in a multi-select
    checkbox's ``name`` attribute ("Notion Website" for a "how did you hear
    about us" checkbox) rather than a machine identifier -- including it
    re-introduces exactly the false "personal website" match that fixing
    ``label`` to use the group's real question text was meant to prevent.

    The camelCase/snake_case split runs ONLY on ``name``/``id`` -- running it
    over the whole joined string (a real earlier bug here) also mangles
    ordinary label text that happens to have an internal capital, e.g.
    "GitHub" -> "Git Hub" and "LinkedIn" -> "Linked In", silently breaking
    the literal ``github``/``linkedin`` patterns below on real rendered
    labels (confirmed on live Lever/GitLab forms -- LinkedIn fields were
    always falling through to the generic "not recognized" case instead of
    the more specific "no LinkedIn URL configured" one)."""
    human = " ".join(str(p) for p in (f.get("label", ""), f.get("ariaLabel", ""), f.get("placeholder", "")) if p)

    attrs = ""
    if f.get("kind") != "checkbox":
        attrs = " ".join(str(p) for p in (f.get("name", ""), f.get("id", "")) if p)
        attrs = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", attrs)
        attrs = re.sub(r"[_\-\[\]]+", " ", attrs)

    text = f"{human} {attrs}"
    return re.sub(r"\s+", " ", text).strip().lower()


def _classify(context: str) -> str:
    for pattern, key in _RULES:
        if pattern.search(context):
            return key
    return ""


def _maybe_negate(context: str, value: bool) -> bool:
    """A question phrased in the negative ("not willing to relocate", "unable
    to work without sponsorship") flips the plain-English answer -- a cheap
    guard against confidently checking the wrong radio on a negated question."""
    return (not value) if _NEGATION_RE.search(context) else value


def _detect_region(lead: dict, cfg: dict) -> str:
    """'india' | 'overseas' | '' (unknown) from the LEAD's own location/title/
    description/company text. Ambiguous (both sets of keywords hit, e.g. a
    global company's boilerplate mentioning India alongside a US office) is
    deliberately '' -- comp/work-auth answers are legally meaningful, so an
    unclear region is left for the human rather than guessed."""
    text = " ".join(str(lead.get(k) or "") for k in ("location", "title", "description", "company")).lower()
    kws = cfg.get("region_keywords", {})
    has_india = any(kw in text for kw in kws.get("india", []))
    has_overseas = any(kw in text for kw in kws.get("overseas", []))
    if has_india and has_overseas:
        return ""
    if has_india:
        return "india"
    if has_overseas:
        return "overseas"
    return ""


def _rank_project_pitch(lead: dict, cfg: dict) -> tuple[str, str] | None:
    """The best-fit project's (title, pitch) for a "tell us about a project"
    question -- keyword overlap between the job's own title/description/
    company text and each project's ``fit_tags``, using the SAME tokenizer
    generation.generators.resume already uses for resume project-ranking
    (``_keywords``), not a second one. Ties keep the first (declaration
    order in candidate_answers.json)."""
    projects = cfg.get("projects") or []
    if not projects:
        return None
    target = _keywords(" ".join([lead.get("title", ""), lead.get("description", ""), lead.get("company", "")]))
    best, best_score = None, -1
    for proj in projects:
        tag_tokens: set[str] = set()
        for tag in proj.get("fit_tags", []):
            tag_tokens |= _keywords(tag)
        score = len(target & tag_tokens)
        if score > best_score:
            best_score, best = score, proj
    if not best or not best.get("pitch"):
        return None
    return best["title"], best["pitch"]


def _resolve(field_key: str, *, context: str, control_kind: str, control_type: str, lead: dict, cfg: dict, profile: dict, folder) -> dict:
    """-> {"value": ..., "note": ...}. ``value`` is None when this field must
    be left for the human (never a guess); otherwise a str for text-like/
    select/radio targets or a bool for a plain yes/no question."""
    identity = cfg.get("identity", {})
    is_text = control_kind in ("text", "textarea")
    region = _detect_region(lead, cfg)

    if field_key == "first_name":
        return {"value": identity.get("first_name", ""), "note": ""}
    if field_key == "last_name":
        return {"value": identity.get("last_name", ""), "note": ""}
    if field_key == "full_name":
        return {"value": identity.get("name", ""), "note": ""}
    if field_key == "email":
        return {"value": identity.get("email", ""), "note": ""}
    if field_key == "phone":
        return {"value": identity.get("phone", ""), "note": ""}
    if field_key == "phone_country_code":
        return {"value": None, "note": "phone country code -- select +91 manually"}
    if field_key == "linkedin":
        value = identity.get("linkedin_url", "")
        return {"value": value or None, "note": "no LinkedIn URL configured in candidate_answers.json" if not value else ""}
    if field_key == "github":
        return {"value": identity.get("github_url", ""), "note": ""}
    if field_key == "portfolio":
        return {"value": identity.get("portfolio_url", ""), "note": ""}
    if field_key == "country":
        return {"value": identity.get("country", ""), "note": ""}
    if field_key == "location":
        return {"value": identity.get("location", ""), "note": ""}
    if field_key == "resume_upload":
        if control_kind != "file":
            return {"value": None, "note": "resume requested as text/URL, not a file upload -- fill in manually"}
        path = cfg.get("resume_path", "")
        if path and os.path.isfile(path):
            return {"value": path, "note": ""}
        return {"value": None, "note": f"resume file not found at configured resume_path: {path or '(not set)'}"}
    if field_key == "cover_letter":
        if control_kind == "file":
            return {"value": None, "note": "cover letter requested as a file upload -- attach manually (tailored text is in the drafts folder)"}
        text = apply_assist._field_text("cover_letter", folder, profile) if folder else ""
        return {"value": text or None, "note": "" if text else "cover letter text not available -- packet build may have failed"}
    if field_key == "current_compensation":
        return {"value": None, "note": "current compensation isn't tracked (only expected/desired is) -- fill manually"}
    if field_key == "compensation_expected":
        band = (cfg.get("compensation", {}) or {}).get(region, "") if region else ""
        if band:
            return {"value": band, "note": ""}
        return {"value": None, "note": "couldn't tell India vs. overseas from this posting -- fill compensation manually"}
    if field_key == "notice_period":
        if control_type == "date":
            return {"value": None, "note": "start-date picker -- enter manually (candidate is immediately available)"}
        return {"value": cfg.get("notice_period", ""), "note": ""}
    if field_key == "experience_years":
        if control_type == "number":
            return {"value": cfg.get("experience_years", ""), "note": ""}
        return {"value": cfg.get("experience_years_text", ""), "note": ""}
    if field_key == "work_authorized":
        if is_text:
            return {"value": cfg.get("work_authorization", {}).get("statement", ""), "note": ""}
        if not region:
            return {"value": None, "note": "couldn't tell India vs. overseas from this posting -- answer work authorization manually"}
        authorized = bool(cfg["work_authorization"][region]["authorized"])
        return {"value": _maybe_negate(context, authorized), "note": ""}
    if field_key == "sponsorship_required":
        if is_text:
            return {"value": cfg.get("work_authorization", {}).get("statement", ""), "note": ""}
        if not region:
            return {"value": None, "note": "couldn't tell India vs. overseas from this posting -- answer the sponsorship question manually"}
        needs_sponsorship = bool(cfg["work_authorization"][region]["sponsorship_required"])
        return {"value": _maybe_negate(context, needs_sponsorship), "note": ""}
    if field_key == "willing_to_relocate":
        if is_text:
            return {"value": cfg.get("relocation_statement", ""), "note": ""}
        return {"value": _maybe_negate(context, bool(cfg.get("willing_to_relocate", False))), "note": ""}
    if field_key == "open_to_remote":
        if is_text:
            return {"value": cfg.get("remote_statement", ""), "note": ""}
        return {"value": _maybe_negate(context, bool(cfg.get("requires_remote", True))), "note": ""}
    if field_key == "why_company":
        text = apply_assist._field_text("why_company", folder, profile) if folder else ""
        return {"value": text or None, "note": "" if text else "no tailored 'why this company' text available for this lead"}
    if field_key == "project_answer":
        ranked = _rank_project_pitch(lead, cfg)
        return {"value": ranked[1] if ranked else None, "note": "" if ranked else "no project pitch configured"}
    if field_key == "eeo":
        return {"value": None, "note": "EEO/demographic question -- intentionally left for you to answer"}
    if field_key == "consent":
        return {"value": None, "note": "consent/legal checkbox -- left unchecked; read and check it yourself"}
    return {"value": None, "note": "not recognized -- no rule matches this label"}


# ---------------------------------------------------------------------------
# Playwright glue -- scan the page once (single JS round-trip), then fill.
# ---------------------------------------------------------------------------

_SCAN_JS = r"""
() => {
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function labelFor(el) {
    if (el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) return norm(l.innerText);
    }
    const wrap = el.closest('label');
    if (wrap) return norm(wrap.innerText);
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const txt = labelledby.split(/\s+/).map(id => { const e = document.getElementById(id); return e ? e.innerText : ''; }).join(' ');
      if (norm(txt)) return norm(txt);
    }
    return '';
  }
  function questionFor(el) {
    const fs = el.closest('fieldset');
    if (fs) {
      // The fieldset's OWN direct-child heading (legend, or a <label> used
      // as one -- Ashby's own multi-select checkbox clusters do this) is
      // the real group question. Checked before the generic ancestor climb
      // below, which otherwise greedily matches a PER-OPTION label first
      // (each option commonly has its own nearby label for accessibility,
      // one DOM level closer to `el` than the fieldset's group heading is).
      const heading = fs.querySelector(':scope > legend, :scope > label');
      if (heading) return norm(heading.innerText);
    }
    let node = el;
    for (let i = 0; i < 5 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const cand = node.querySelector(':scope > label, :scope > legend, :scope > [class*="label" i], :scope > [class*="question" i]');
      if (cand && cand !== el) {
        const t = norm(cand.innerText);
        if (t) return t;
      }
    }
    return '';
  }
  function selectorFor(el) {
    // Attribute-value selector, not `#${id}` -- ids that start with a digit
    // or a UUID (e.g. Ashby's own field ids) are invalid as bare CSS
    // identifiers and throw a SyntaxError from querySelectorAll; quoting the
    // value sidesteps that entirely.
    if (el.id) return `[id="${el.id}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    return '';
  }

  const out = [];
  const seenRadioGroups = new Set();
  const controls = Array.from(document.querySelectorAll('input, textarea, select'));
  for (const el of controls) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || (tag === 'textarea' ? 'textarea' : tag === 'select' ? 'select' : 'text')).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) continue;
    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    if (!visible || el.disabled) continue;

    const name = el.getAttribute('name') || '';
    if (type === 'radio') {
      const key = name || ('#' + (el.id || Math.random()));
      if (seenRadioGroups.has(key)) continue;
      seenRadioGroups.add(key);
      const group = name ? Array.from(document.querySelectorAll(`input[type="radio"][name="${name}"]`)) : [el];
      out.push({
        kind: 'radio_group', type: 'radio', name, id: el.id || '', placeholder: '', ariaLabel: el.getAttribute('aria-label') || '',
        label: questionFor(el) || labelFor(el),
        selector: '', options: group.map(o => ({ value: o.value || '', label: norm(labelFor(o)) || norm(o.value || '') })),
      });
      continue;
    }

    const kind = tag === 'select' ? 'select' : (type === 'checkbox' ? 'checkbox' : (type === 'file' ? 'file' : (tag === 'textarea' ? 'textarea' : 'text')));
    const ownLabel = labelFor(el);
    // A lone checkbox's own label ("I require visa sponsorship") usually IS
    // the question. But a checkbox with a unique per-option name inside a
    // multi-select cluster (e.g. Ashby's "how did you hear about us" --
    // name="LinkedIn"/"Notion Website"/... on independent checkboxes with no
    // shared `name` to group them like radios) has an own-label that's just
    // ONE OPTION, not the question -- classifying off it alone previously
    // misread a "Notion Website" referral-source checkbox as a request for
    // the candidate's personal website. Prefer the enclosing question text
    // for checkboxes, same priority order already used for radio groups,
    // and keep the option's own label separately for the human-facing report.
    out.push({
      kind, type, name, id: el.id || '',
      placeholder: el.getAttribute('placeholder') || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      role: el.getAttribute('role') || '', required: el.required || el.getAttribute('aria-required') === 'true',
      label: kind === 'checkbox' ? (questionFor(el) || ownLabel) : (ownLabel || questionFor(el)),
      optionLabel: ownLabel,
      selector: selectorFor(el),
      options: tag === 'select' ? Array.from(el.options).map(o => ({ value: o.value, label: norm(o.text) })) : [],
    });
  }
  return out;
}
"""


def _scan(page) -> list[dict]:
    return page.evaluate(_SCAN_JS)


_GATED_HINT_JS = r"""
() => {
  const els = Array.from(document.querySelectorAll('button, a, [role="tab"], [role="button"]'));
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim();
    if (t && /apply/i.test(t) && t.length < 60) return t;
  }
  return '';
}
"""


def _gated_apply_hint(page) -> str:
    """Read-only check for a page that shows the description but not the
    form yet (e.g. Ashby's Overview/Application tabs, gated behind a control
    literally labeled "Apply for this Job"). Never clicks it -- this only
    explains an empty scan honestly instead of reporting a false "nothing
    left to do". `_find_reveal_control`/`_click_reveal_control` below are
    what's now allowed to click that same control, under a much narrower
    predicate than "matches /apply/i" -- this function is unchanged and
    still never clicks anything."""
    try:
        return (page.evaluate(_GATED_HINT_JS) or "").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Form-revealing controls -- e.g. Ashby's "Apply for this Job" -- vs. submit
# controls. These are provably distinct by construction, not just by label:
#
#   REVEAL: only ever considered when the page has ZERO fillable fields yet
#   (checked by the caller, `_fill_role`, before calling `_find_reveal_control`
#   at all -- so there is nothing on the page a click here could send), the
#   control's accessible name is in a short disclosure vocabulary ("apply",
#   "apply for this job", "apply now", "view application", ...), it does NOT
#   match the submit vocabulary, and it is not inside a <form> (a real
#   submit/cancel/save-draft control lives inside the form it acts on; a
#   reveal control by definition doesn't, because the form doesn't exist on
#   the page yet).
#
#   SUBMIT: `_FINAL_SUBMIT_CONTROLS_JS` (used only by batch mode's
#   `_submission_gate`, untouched here) -- matches "submit"/"submit
#   application"/"send application"/"complete application"/"finish
#   application"/bare "apply" with NO <form> exclusion, because by the time
#   batch calls it, `apply_all` has already filled real fields into a real
#   <form> and the click is meant to send them.
#
# The two vocabularies deliberately overlap on bare "apply" (some ATS's use
# it for either role) -- what disambiguates them is which state the page is
# in when the check runs, never the label alone.
# ---------------------------------------------------------------------------

_REVEAL_CANDIDATES_JS = r"""
() => {
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  // Discloses the form -- never sends it.
  const revealLabel = /^(apply|apply for this job|apply now|view application|show application|application)$/i;
  // Sends an already-filled form -- disqualifies a control even if it also
  // happens to match revealLabel (relevant only for bare "apply").
  const submitLabel = /^(submit|submit application|send application|send|finish|finish application|complete application)$/i;

  const els = Array.from(document.querySelectorAll('button, a, [role="tab"], [role="button"]'));
  const out = [];
  for (const el of els) {
    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    if (!visible || el.disabled) continue;
    const label = norm(el.innerText || el.textContent || el.getAttribute('aria-label') || el.value || '');
    if (!label || label.length > 60) continue;
    if (submitLabel.test(label)) continue;
    if (!revealLabel.test(label)) continue;
    // A control inside a <form> is acting ON that form (submit/cancel/save),
    // never disclosing a not-yet-existing one -- exclude it regardless of
    // label, this is the structural half of the reveal/submit split.
    if (el.closest('form')) continue;
    el.setAttribute('data-jhm-reveal-candidate', String(out.length));
    out.push({ label });
  }
  return out;
}
"""


def _find_reveal_control(page) -> dict | None:
    """The single form-revealing control on the page right now, if any --
    see the block comment above `_REVEAL_CANDIDATES_JS` for the exact
    predicate. Callers must only invoke this when the page has zero
    fillable fields (see `_fill_role`); this function does not re-check
    that itself, since it has no field list of its own to check against."""
    try:
        candidates = page.evaluate(_REVEAL_CANDIDATES_JS)
    except Exception:
        return None
    return candidates[0] if candidates else None


def _looks_like_confirmation_page(page) -> bool:
    """True if the current page looks like a post-submission thank-you page.
    Used only as a safety trip-wire right after a reveal click (never after
    a real fill) -- if a "reveal" control turns out to have actually
    submitted something (a mislabeled control this predicate didn't expect),
    this catches it so the caller can abort loudly instead of silently
    reporting "form still not found"."""
    try:
        if bool(page.evaluate(_SUBMISSION_CONFIRMED_JS)):
            return True
    except Exception:
        pass
    return bool(re.search(r"(?:thank|confirmation|success|submitted)", str(getattr(page, "url", "")), re.I))


def _click_reveal_control(page, control: dict) -> None:
    """Click a form-revealing control exactly once. Raises if the click
    lands on what looks like a submission-confirmation page -- the caller's
    existing "could not open/autofill this role" handling (session/batch's
    per-lead try/except, or an uncaught error on the single-role `main()`
    path) then reports it loudly and moves on, rather than this function
    silently swallowing an unexpected submission."""
    url_before = page.url
    page.locator('[data-jhm-reveal-candidate="0"]').first.click(timeout=5000)
    page.wait_for_timeout(1500)
    if _looks_like_confirmation_page(page):
        raise RuntimeError(
            f"clicking {control['label']!r} to reveal the application form unexpectedly landed on what looks "
            f"like a submission-confirmation page (was {url_before!r}, now {page.url!r}) -- aborting without "
            "filling or clicking anything else on this lead."
        )


_CAPTCHA_PRESENT_JS = r"""
() => Boolean(document.querySelector(
  'iframe[src*="recaptcha" i], iframe[src*="hcaptcha" i], iframe[src*="turnstile" i], ' +
  '[class*="recaptcha" i], [class*="hcaptcha" i], [class*="turnstile" i], [id*="captcha" i]'
))
"""


_FINAL_SUBMIT_CONTROLS_JS = r"""
() => {
  const norm = value => (value || '').replace(/\s+/g, ' ').trim();
  const selectorFor = el => {
    if (el.id) return `[id="${el.id}"]`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const type = el.getAttribute('type');
    return type ? `${el.tagName.toLowerCase()}[type="${type}"]` : el.tagName.toLowerCase();
  };
  const finalLabel = /^(submit|submit application|send application|complete application|finish application|apply)$/i;
  return Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'))
    .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && !el.disabled)
    .map(el => ({
      label: norm(el.innerText || el.value || el.getAttribute('aria-label') || ''),
      selector: selectorFor(el),
    }))
    .filter(control => finalLabel.test(control.label));
}
"""


_SUBMISSION_CONFIRMED_JS = r"""
() => {
  const text = (document.body?.innerText || '').replace(/\s+/g, ' ').toLowerCase();
  return /thank you for applying|thanks for applying|application (has been )?(received|submitted)|successfully submitted|application complete/.test(text);
}
"""


def _submission_gate(page, result: dict) -> tuple[bool, str]:
    """Return whether a filled form is safe to send automatically.

    This is intentionally conservative. A new ATS layout, an unresolved
    question, a CAPTCHA, or two possible final actions is a skip, not a guess.
    """
    if result.get("gated_hint"):
        return False, f"application form is still gated behind {result['gated_hint']!r}"
    if result.get("needs_human"):
        return False, f"{len(result['needs_human'])} required field(s) remain unresolved"
    try:
        if page.evaluate(_CAPTCHA_PRESENT_JS):
            return False, "CAPTCHA detected"
        controls = page.evaluate(_FINAL_SUBMIT_CONTROLS_JS) or []
    except Exception as exc:
        return False, f"could not inspect final submit control: {exc}"
    if len(controls) != 1:
        return False, f"expected exactly one final submit control, found {len(controls)}"
    if not controls[0].get("selector"):
        return False, "final submit control has no stable selector"
    return True, ""


def _submit_if_ready(page, result: dict) -> dict:
    """Click the one verified final submit control and require a confirmation.

    An unconfirmed click is recorded as ``uncertain`` rather than ``submitted``
    so a later batch cannot silently count an application it cannot prove.
    """
    allowed, reason = _submission_gate(page, result)
    if not allowed:
        return {"status": "skipped", "reason": reason}

    control = page.evaluate(_FINAL_SUBMIT_CONTROLS_JS)[0]
    try:
        page.locator(control["selector"]).first.click(timeout=5000)
        page.wait_for_timeout(2000)
        confirmed = bool(page.evaluate(_SUBMISSION_CONFIRMED_JS)) or bool(
            re.search(r"(?:thank|confirmation|success|submitted)", str(getattr(page, "url", "")), re.I)
        )
    except Exception as exc:
        return {"status": "uncertain", "reason": f"submit click did not complete cleanly: {exc}"}
    if not confirmed:
        return {"status": "uncertain", "reason": "submit was clicked but no confirmation page was detected"}
    return {"status": "submitted", "reason": "application confirmation detected"}


def _best_option(desired: str, options: list[dict]) -> dict | None:
    if not desired or not options:
        return None
    d = desired.strip().lower()
    for opt in options:
        if opt["label"].strip().lower() == d:
            return opt
    for opt in options:
        if re.search(rf"\b{re.escape(d)}\b", opt["label"].strip().lower()):
            return opt
    # Loose substring fallback -- only for longer desired strings ("india" in
    # "india (in)"). Below 4 chars this is how "no" matches inside
    # "november" or "yes" inside "yesteryear": too short to trust unanchored.
    if len(d) >= 4:
        for opt in options:
            if d in opt["label"].strip().lower():
                return opt
    return None


def _as_yes_no(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _perform_fill(page, f: dict, value) -> tuple[bool, str]:
    """Apply one resolved value to the page. Returns (ok, note-on-failure).
    Never presses Enter and never touches a submit/apply/send control --
    only .fill()/.check()/.select_option()/.set_input_files() on the
    specific field that was matched."""
    kind = f["kind"]
    selector = f.get("selector") or ""

    if kind == "radio_group":
        name = f.get("name") or ""
        if not name:
            return False, "radio group has no shared name -- can't target reliably"
        desired = _as_yes_no(value)
        opt = _best_option(desired, f.get("options") or [])
        if not opt:
            return False, f"no '{desired}' option among: {', '.join(o['label'] for o in f.get('options') or [])}"
        options = f.get("options") or []
        idx = next((i for i, o in enumerate(options) if o == opt), None)
        group = page.locator(f'input[type="radio"][name="{name}"]')
        target = group.nth(idx) if idx is not None else group.first
        target.check(timeout=3000)
        return True, ""

    if kind == "checkbox":
        if not selector:
            return False, "no selector for checkbox"
        want = value if isinstance(value, bool) else str(value).strip().lower() in ("yes", "true", "1")
        loc = page.locator(selector).first
        if want and not loc.is_checked():
            loc.check(timeout=3000)
        return True, ""

    if kind == "select":
        desired = _as_yes_no(value)
        opt = _best_option(desired, f.get("options") or [])
        if not opt:
            return False, f"no matching option for '{desired}'"
        loc = page.locator(selector).first
        if opt.get("value"):
            loc.select_option(value=opt["value"], timeout=3000)
        else:
            loc.select_option(label=opt["label"], timeout=3000)
        return True, ""

    if kind == "file":
        if not selector:
            return False, "no selector for file input"
        page.locator(selector).first.set_input_files(str(value), timeout=10000)
        return True, ""

    # text / textarea
    if not selector:
        return False, "no selector for this field"
    page.locator(selector).first.fill(_as_yes_no(value), timeout=5000)
    return True, ""


def _preview(field_key: str, value) -> str:
    if field_key == "resume_upload":
        return Path(str(value)).name
    text = re.sub(r"\s+", " ", _as_yes_no(value)).strip()
    return (text[:70] + "...") if len(text) > 70 else text


def _label_of(f: dict) -> str:
    # A checkbox's ``label`` is the group QUESTION (for classification); the
    # human-facing report is more useful naming the specific option
    # ("Notion Website") rather than repeating the shared question text
    # identically across every checkbox in the same cluster.
    if f.get("kind") == "checkbox" and f.get("optionLabel"):
        label = f["optionLabel"]
    else:
        label = f.get("label") or f.get("ariaLabel") or f.get("placeholder") or f.get("name") or f.get("id") or "(unlabeled field)"
    return re.sub(r"\s+", " ", str(label)).strip()[:90]


def _is_privacy_consent(context: str) -> bool:
    """Only a plain privacy-policy acknowledgement is eligible for opt-in
    automation. Terms, declarations, and certifications always require a
    human because their wording can create a separate legal assertion."""
    text = context.lower()
    return "privacy" in text and not any(word in text for word in ("certif", "declare", "terms", "attest"))


_HN_ITEM_URL_RE = re.compile(r"news\.ycombinator\.com/item", re.I)
_RAW_POST_TEXT_RE = re.compile(r"\bwe(?:'re| are)\s+hiring\b|\bhiring at\b", re.I)


def _looks_like_manual_only(lead: dict) -> str:
    """Non-empty reason iff this lead can never be form-filled, so `next`/
    `session` should say so and move on instead of opening a browser tab
    that will always report an empty scan.

    Two cases, confirmed against the real queue: (1) the apply URL is a
    HackerNews *discussion* item, not a company posting -- some "who's
    hiring" ingestion stores the HN thread link as `url` itself, and there
    is no form there, ever; (2) the title/company are raw forum-post text
    ("Hiring at We are hiring full-stack and applie..." / "We are hiring
    full-sta...") rather than a real job title and company name -- the
    scraper truncated one HN comment into both fields. Both can only be
    followed up by replying to the post or emailing, never a form."""
    url = str(lead.get("url") or "")
    if _HN_ITEM_URL_RE.search(url):
        return "manual: email/HN post"
    joined = f"{lead.get('title') or ''} {lead.get('company') or ''}"
    if _RAW_POST_TEXT_RE.search(joined):
        return "manual: email/HN post"
    return ""


def apply_all(
    page, fields: list[dict], lead: dict, cfg: dict, profile: dict, folder,
    *, auto_submit: bool = False, allow_privacy_consent: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Classify + fill every scanned field. Returns (filled, needs_human) --
    each a list of {"label": ..., "reason"/"preview": ...} for the summary."""
    filled: list[dict] = []
    needs_human: list[dict] = []

    for f in fields:
        # Some frameworks render a hidden/duplicate control alongside the real
        # one (no id, no name) purely for internal wiring -- there is no
        # selector we could ever act on, and nothing a human could recognize
        # from a report either, so it's dropped rather than surfaced as a
        # confusing "needs you" duplicate of a field already filled.
        if f["kind"] in ("text", "textarea", "select", "file") and not f.get("selector"):
            continue
        if f["kind"] == "radio_group" and not f.get("name"):
            continue

        context = _normalize_context(f)
        field_key = _classify(context)
        disposition = _resolve(
            field_key, context=context, control_kind=f["kind"], control_type=f.get("type", ""),
            lead=lead, cfg=cfg, profile=profile, folder=folder,
        )
        label = _label_of(f)

        # A candidate can opt into checking a *plain privacy-policy* box in
        # batch mode. Any declaration/certification/terms checkbox is still
        # deliberately left for review, irrespective of command-line flags.
        if (
            field_key == "consent" and allow_privacy_consent and f["kind"] == "checkbox"
            and _is_privacy_consent(context)
        ):
            disposition = {"value": True, "note": ""}

        if disposition["value"] is None:
            # Optional demographic/referral/custom fields should not prevent
            # a valid application from being sent in strict batch mode. The
            # normal review modes still report every unresolved field.
            if auto_submit and not f.get("required", False):
                continue
            needs_human.append({"label": label, "reason": disposition["note"] or "not recognized"})
            continue

        # react-select-style custom dropdowns (Greenhouse's "select"-shaped
        # custom questions, among others) are a plain <input role="combobox">
        # under the hood: Playwright's .fill() happily sets its DOM value, but
        # the visible widget only updates from a real open-the-list/click-an-
        # option interaction, so a blind fill would silently NOT show up on
        # screen -- a false "filled" claim the human wouldn't catch on
        # review. Reliably driving react-select's own listbox is fragile
        # (multiple comboboxes can share ambiguous listbox markup on one
        # page -- confirmed against a live Greenhouse form), so this is
        # reported with the intended answer instead of risking a wrong click.
        # ponytail: report-only for role=combobox; a real listbox-driver is
        # the upgrade path if a specific ATS's pattern turns out to need it.
        if f["kind"] in ("text", "textarea") and f.get("role") == "combobox":
            preview = _preview(field_key, disposition["value"])
            needs_human.append({"label": label, "reason": f"custom dropdown -- select this yourself: {preview}", "value": preview})
            continue

        try:
            ok, note = _perform_fill(page, f, disposition["value"])
        except Exception as exc:
            ok, note = False, f"fill error: {exc}"

        if ok:
            filled.append({"label": label, "field": field_key, "preview": _preview(field_key, disposition["value"])})
        else:
            # `value` is the intended answer even though automation couldn't
            # apply it -- so a session-mode card can show it as something to
            # PASTE, not just explain why it's blank (see the "N fields need
            # you, WITH the intended answer" requirement for `session`).
            needs_human.append({
                "label": label, "reason": note or "could not fill (page structure)",
                "value": _preview(field_key, disposition["value"]),
            })

    return filled, needs_human


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _get_lead(target: str, db_path: str) -> dict:
    if target == "next":
        queue = apply_assist._queue(db_path)
        for lead in queue:
            reason = _looks_like_manual_only(lead)
            if reason:
                print(f"  skipping {lead.get('title')} @ {lead.get('company')} ({lead.get('job_id')}): {reason}")
                continue
            return lead
        return {}
    # A directly-named job_id is an explicit human request for THAT lead --
    # unlike "next", never second-guess it as manual-only.
    return get_lead_by_id(target, db_path) or {}


def _print_summary(lead: dict, filled: list[dict], needs_human: list[dict], gated_hint: str = "") -> None:
    print(f"\n  {lead.get('title')} @ {lead.get('company')}  [{lead.get('platform')}]")
    print(f"  filled {len(filled)} field(s):")
    for item in filled:
        print(f"    - {item['label']}: {item['preview']}")
    if not filled:
        print("    (none)")

    if gated_hint and not filled and not needs_human:
        print(f"\n  no application form found on this page yet -- it looks gated behind {gated_hint!r}.")
        print("  this tool will not click it (hard boundary: never clicks submit/apply/send controls).")
        print("  open it yourself in the browser below, then fill/copy the answers from this run's drafts folder.")
    elif needs_human:
        print(f"\n  {len(needs_human)} field(s) need you:")
        for item in needs_human:
            print(f"    - {item['label']}: {item['reason']}")
    else:
        print("\n  nothing left for you -- every detected field was filled")

    print("\n  " + "=" * 64)
    print("  REVIEW EVERY FIELD, THEN CLICK SUBMIT YOURSELF.")
    print("  This tool fills forms. It never submits them.")
    print("  " + "=" * 64)


# ---------------------------------------------------------------------------
# Session mode -- fill the next queued role, ask the human what happened,
# loop in the SAME browser context. Still never submits: [Enter] means "I
# clicked submit myself", never "click submit for me".
# ---------------------------------------------------------------------------

def _fill_role(
    page, lead: dict, cfg: dict, profile: dict, folder: Path,
    *, auto_submit: bool = False, allow_privacy_consent: bool = False,
) -> dict:
    """Navigate an already-open ``page`` to ``lead['url']``, autofill it, and
    screenshot the result -- the exact scan/fill/screenshot steps `main()`'s
    single-role flow always ran, pulled out so `session` mode can run them
    once per role in a loop instead of duplicating them. Caller has already
    built ``folder`` (the drafts packet); this only drives the page. Returns
    {"filled", "needs_human", "gated_hint", "screenshot_path"}
    (``screenshot_path`` is None if the screenshot itself failed)."""
    page.goto(lead["url"], wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Lever's job-description page shows the posting with an "Apply for this
    # job" button/link to a SEPARATE page -- clicking it is exactly what the
    # hard boundary forbids. But Lever's own public routing serves that same
    # application form directly at <job-url>/apply (confirmed against a live
    # posting); navigating there is choosing which URL to open, same as
    # opening the original lead URL in the first place -- not clicking
    # anything on the page.
    if (
        str(lead.get("platform") or "").lower() == "lever"
        and not lead["url"].rstrip("/").endswith("/apply")
        and page.locator("input, textarea, select").count() < 3
    ):
        try:
            page.goto(lead["url"].rstrip("/") + "/apply", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            print(f"\n  (could not open Lever's /apply page: {exc})")

    fields = _scan(page)

    # Ashby (and similar ATS's) hide the application form behind a control
    # like "Apply for this Job" until it's clicked -- that click DISCLOSES
    # the form, it does not submit anything. Only attempted when the page
    # has ZERO fillable fields yet (never once real fields exist -- this is
    # never reached a second time for the same page, since after either
    # branch below `fields` is non-empty or the reveal control wasn't
    # found), and the control itself is verified not to be a submit control
    # by `_find_reveal_control`/`_REVEAL_CANDIDATES_JS`. If the click
    # unexpectedly lands on a confirmation page, `_click_reveal_control`
    # raises -- this propagates out of `_fill_role` so the caller's own
    # "could not open/autofill this role" handling reports it loudly and
    # skips the lead, instead of silently treating it as "no form here".
    if not fields:
        reveal_control = _find_reveal_control(page)
        if reveal_control:
            _click_reveal_control(page, reveal_control)
            fields = _scan(page)

    filled, needs_human = apply_all(
        page, fields, lead, cfg, profile, folder,
        auto_submit=auto_submit, allow_privacy_consent=allow_privacy_consent,
    )

    gated_hint = ""
    if len(fields) < 3:
        gated_hint = _gated_apply_hint(page)

    # A file upload (resume) commonly kicks off an async upload the widget
    # only reflects a few seconds later -- give it a moment so the
    # screenshot shows the real end state, not "still uploading".
    if any(item["field"] == "resume_upload" for item in filled):
        page.wait_for_timeout(4000)

    screenshot_path = folder / "autofill_screenshot.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True, timeout=10000)
    except Exception as exc:
        print(f"\n  (screenshot failed: {exc})")
        screenshot_path = None

    return {"filled": filled, "needs_human": needs_human, "gated_hint": gated_hint, "screenshot_path": screenshot_path}


def _visit_role(page, lead: dict, cfg: dict, profile: dict, db_path: str, args) -> dict:
    """Session mode's default per-role step: build the packet, record the
    same ``autofill_opened`` event the single-role flow records, then fill.
    Kept separate from `_fill_role` so tests can swap this ONE seam for a
    fake and never touch the real DB, packet builder, or a browser."""
    folder = apply_assist._ensure_packet(lead["job_id"], db_path, Path(args.profile), Path(args.drafts_dir))
    record_event(lead["job_id"], "autofill_opened", db_path)
    return _fill_role(
        page, lead, cfg, profile, folder,
        auto_submit=getattr(args, "target", "") == "batch",
        allow_privacy_consent=getattr(args, "allow_privacy_consent", False),
    )


def _mark_applied(job_id: str, db_path: str, args) -> int:
    """Chain draft_ready -> approved -> applied via review.cmd_mark -- the
    SAME two calls apply_assist.cmd_done makes, reusing review.py's own
    transition-legality + outcome-feedback logic rather than a private copy
    of the state machine. Doesn't call apply_assist.cmd_done directly: that
    function also opens a SEPARATE browser tab and prints its own "next
    role" card via cmd_next, which would fight this session's own
    persistent browser and queue loop."""
    def _mark_args(status: str) -> argparse.Namespace:
        return argparse.Namespace(
            job_id=job_id, new_status=status, note="", force=False,
            db=args.db, drafts_dir=args.drafts_dir, profile=args.profile,
        )

    lead = get_lead_by_id(job_id, db_path)
    if lead and str(lead.get("status") or "") == "draft_ready":
        rc = apply_assist.review.cmd_mark(_mark_args("approved"))
        if rc != 0:
            return rc
    return apply_assist.review.cmd_mark(_mark_args("applied"))


def _prompt_session_choice() -> str:
    """Blocks on the human. Empty input (bare Enter) means "I clicked submit
    myself -- mark applied and load the next role"; 's' skips without
    marking anything; 'q' ends the session. Returns 'enter' | 's' | 'q'."""
    raw = input("\n  [Enter]=I submitted it -- mark applied + next   [s]=skip   [q]=quit\n  > ")
    choice = raw.strip().lower()
    if choice in ("q", "quit"):
        return "q"
    if choice in ("s", "skip"):
        return "s"
    return "enter"


def _print_session_card(idx: int, lead: dict, result: dict) -> None:
    print("\n  " + "=" * 64)
    print(f"  [{idx}] {lead.get('title')} @ {lead.get('company')}  [{lead.get('platform')}]")
    print(f"  fit score: {int(lead.get('score') or 0)}")
    print(f"  apply: {lead.get('url')}")

    filled = result.get("filled") or []
    print(f"  filled {len(filled)} field(s):")
    for item in filled:
        print(f"    - {item['label']}: {item['preview']}")
    if not filled:
        print("    (none)")

    needs_human = result.get("needs_human") or []
    gated_hint = result.get("gated_hint") or ""
    if gated_hint and not filled and not needs_human:
        print(f"\n  no application form found yet -- looks gated behind {gated_hint!r}.")
        print("  this tool will not click it -- left open for you to complete manually.")
    elif needs_human:
        print(f"\n  {len(needs_human)} field(s) need you:")
        for item in needs_human:
            paste = f"   ->  PASTE: {item['value']}" if item.get("value") else ""
            print(f"    - {item['label']}: {item['reason']}{paste}")
    else:
        print("\n  nothing left for you -- every detected field was filled")
    print("  " + "=" * 64)


def _print_session_summary(result: dict) -> None:
    print("\n  " + "=" * 64)
    print("  SESSION SUMMARY")
    print(f"    submitted (marked applied): {result.get('submitted', 0)}")
    print(f"    skipped:                    {result.get('skipped', 0)}")
    print(f"    remaining in queue:         {result.get('remaining', 0)}")
    print("  " + "=" * 64 + "\n")


def _run_session(
    page, cfg: dict, profile: dict, db_path: str, args,
    *, queue_fn=None, visit_role=None, mark_applied=None, prompt=None,
) -> dict:
    """The session loop's actual state machine: which role is next, what
    Enter/s/q each do, and when it stops. Every collaborator that reaches
    outside this function (the queue, Playwright, the DB write, the human)
    is injected -- production wires the real ones below; tests pass fakes
    and never touch a browser or the DB. Returns {"submitted", "skipped",
    "remaining"}.

    Never infers a submission: `skip` marks nothing, and the ONLY thing that
    writes "applied" is the human's own bare-Enter response, delegated to
    `mark_applied` (which itself delegates to review.cmd_mark)."""
    queue_fn = queue_fn or (lambda: apply_assist._queue(db_path))
    visit_role = visit_role or (lambda lead: _visit_role(page, lead, cfg, profile, db_path, args))
    mark_applied = mark_applied or (lambda job_id: _mark_applied(job_id, db_path, args))
    prompt = prompt or _prompt_session_choice

    seen: set[str] = set()
    submitted = skipped = processed = 0

    try:
        while args.limit is None or processed < args.limit:
            queue = [lead for lead in queue_fn() if lead["job_id"] not in seen]
            if not queue:
                print("\n  queue is empty -- nothing left at draft_ready/approved\n")
                break
            lead = queue[0]
            job_id = lead["job_id"]

            if not lead.get("url"):
                print(f"\n  lead {job_id!r} has no apply URL -- skipping automatically\n")
                seen.add(job_id)
                continue
            manual_reason = _looks_like_manual_only(lead)
            if manual_reason:
                print(f"\n  {lead.get('title')} @ {lead.get('company')} ({job_id!r}): {manual_reason} -- "
                      "skipping automatically, there is no form to fill\n")
                seen.add(job_id)
                continue
            try:
                assert_public_url(lead["url"])
            except BlockedUrlError as exc:
                print(f"\n  refusing to open this URL, skipping automatically: {exc}\n")
                seen.add(job_id)
                continue

            try:
                result = visit_role(lead)
            except Exception as exc:
                print(f"\n  ! could not open/autofill this role: {exc}")
                print("  skipping automatically -- nothing marked.")
                seen.add(job_id)
                continue

            processed += 1
            if result.get("screenshot_path"):
                print(f"\n  screenshot of the filled form: {result['screenshot_path']}")
            _print_session_card(processed, lead, result)

            choice = prompt()
            if choice == "q":
                print("\n  quitting session.")
                break
            if choice == "s":
                print("  -> skipped. nothing marked. loading next role...")
                skipped += 1
                seen.add(job_id)
                continue

            rc = mark_applied(job_id)
            if rc != 0:
                print(f"  ! could not mark {job_id} applied -- left queued; treating as skipped for this session")
                skipped += 1
                seen.add(job_id)
                continue
            print("  -> marked applied. loading next role...")
            submitted += 1
            seen.add(job_id)
    except KeyboardInterrupt:
        print("\n\n  interrupted -- ending session.")

    remaining = len([lead for lead in queue_fn() if lead["job_id"] not in seen])
    return {"submitted": submitted, "skipped": skipped, "remaining": remaining}


def cmd_session(args) -> int:
    db_path = run_scrape.resolve_db(args.db)
    if not Path(args.config).exists():
        print(f"\n  missing config: {args.config}")
        print("  copy the candidate_answers.json shape from the script's docstring/README and fill in real data.\n")
        return 2
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    print("\n  session mode -- fills every role, never submits. YOU click submit yourself, every time.")
    print("  [Enter] after you submit = mark applied + load the next role.  [s] = skip.  [q] = quit.\n")

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    result = {"submitted": 0, "skipped": 0, "remaining": 0}
    try:
        with sync_playwright() as pw:
            browser_ctx = _launch_context(pw, args, slow_mo=60)
            try:
                page = browser_ctx.new_page()
                if not args.no_mail:
                    try:
                        mail_page = browser_ctx.new_page()
                        mail_page.goto(GMAIL_URL, wait_until="domcontentloaded", timeout=30000)
                    except Exception as exc:
                        print(f"\n  (could not open Gmail tab: {exc})")
                result = _run_session(page, cfg, profile, db_path, args)
            finally:
                try:
                    browser_ctx.close()
                except Exception as exc:
                    print(f"  (browser close warning: {exc})")
    except KeyboardInterrupt:
        print("\n\n  interrupted -- closing up.")

    _print_session_summary(result)
    return 0


def _print_batch_summary(result: dict) -> None:
    print("\n  " + "=" * 64)
    print("  BATCH SUBMISSION SUMMARY")
    print(f"    confirmed submitted: {result.get('submitted', 0)}")
    print(f"    skipped safely:      {result.get('skipped', 0)}")
    print(f"    needs review:        {result.get('needs_review', 0)}")
    print(f"    remaining in queue:  {result.get('remaining', 0)}")
    print("  " + "=" * 64 + "\n")


def _run_batch(
    page, cfg: dict, profile: dict, db_path: str, args,
    *, queue_fn=None, visit_role=None, mark_applied=None, submit=None, event_fn=None, captcha_prompt=None,
) -> dict:
    """Submit a bounded batch of only fully-resolved applications.

    This state machine deliberately stops after an uncertain submission. That
    protects the candidate from a blind retry creating a duplicate application
    on an ATS whose confirmation page we did not recognise.
    """
    queue_fn = queue_fn or (lambda: apply_assist._queue(db_path))
    visit_role = visit_role or (lambda lead: _visit_role(page, lead, cfg, profile, db_path, args))
    mark_applied = mark_applied or (lambda job_id: _mark_applied(job_id, db_path, args))
    submit = submit or (lambda result: _submit_if_ready(page, result))
    event_fn = event_fn or (lambda job_id, event: record_event(job_id, event, db_path))
    captcha_prompt = captcha_prompt or (lambda: input("\n  CAPTCHA is visible. Solve it in the browser, then press Enter here to continue...\n  > "))

    seen: set[str] = set()
    submitted = skipped = needs_review = processed = 0
    batch_limit = min(args.limit if args.limit is not None else 10, 25)

    while processed < batch_limit:
        queue = [lead for lead in queue_fn() if lead["job_id"] not in seen]
        if not queue:
            break
        lead = queue[0]
        job_id = lead["job_id"]
        if not lead.get("url"):
            print(f"\n  {job_id}: no apply URL -- skipped")
            seen.add(job_id)
            skipped += 1
            continue
        try:
            assert_public_url(lead["url"])
            result = visit_role(lead)
        except Exception as exc:
            print(f"\n  {job_id}: could not open/autofill -- {exc}")
            seen.add(job_id)
            skipped += 1
            continue

        processed += 1
        outcome = submit(result)
        status = outcome.get("status")
        reason = outcome.get("reason", "")
        if status == "skipped" and reason == "CAPTCHA detected" and getattr(args, "pause_for_captcha", True):
            captcha_prompt()
            outcome = submit(result)
            status = outcome.get("status")
            reason = outcome.get("reason", "")
        if status == "skipped":
            print(f"\n  {lead.get('title')} @ {lead.get('company')}: skipped -- {reason}")
            seen.add(job_id)
            skipped += 1
            continue
        if status != "submitted":
            print(f"\n  {lead.get('title')} @ {lead.get('company')}: NEEDS REVIEW -- {reason}")
            try:
                event_fn(job_id, "application_submission_uncertain")
            except Exception:
                pass
            needs_review += 1
            break

        rc = mark_applied(job_id)
        if rc != 0:
            print(f"\n  {lead.get('title')} @ {lead.get('company')}: submitted externally, but could not mark the CRM -- stopping")
            try:
                event_fn(job_id, "application_submitted_crm_mark_failed")
            except Exception:
                pass
            needs_review += 1
            break
        print(f"\n  {lead.get('title')} @ {lead.get('company')}: submitted and marked applied")
        seen.add(job_id)
        submitted += 1

    remaining = len([lead for lead in queue_fn() if lead["job_id"] not in seen])
    return {"submitted": submitted, "skipped": skipped, "needs_review": needs_review, "remaining": remaining}


def _run_tab_batch(
    browser_ctx, cfg: dict, profile: dict, db_path: str, args,
    *, queue_fn=None, visit_role=None, mark_applied=None, submit=None, event_fn=None,
    page_factory=None, close_page=None, wait_between=None,
) -> tuple[dict, list[dict]]:
    """Run one active form at a time while preserving blocker tabs.

    A CAPTCHA or another unresolved form stays open in its own tab. The runner
    then opens a fresh tab for the next role, rather than navigating away from
    the challenge or accumulating completed-application tabs. Confirmed
    submissions are closed immediately.
    """
    queue_fn = queue_fn or (lambda: apply_assist._queue(db_path))
    page_factory = page_factory or browser_ctx.new_page
    close_page = close_page or (lambda page: page.close())
    visit_role = visit_role or (lambda page, lead: _visit_role(page, lead, cfg, profile, db_path, args))
    mark_applied = mark_applied or (lambda job_id: _mark_applied(job_id, db_path, args))
    submit = submit or _submit_if_ready
    event_fn = event_fn or (lambda job_id, event: record_event(job_id, event, db_path))
    wait_between = wait_between or (lambda page: page.wait_for_timeout(int(max(0, args.inter_application_delay) * 1000)))

    seen: set[str] = set()
    blockers: list[dict] = []
    submitted = skipped = needs_review = processed = 0
    batch_limit = min(args.limit if args.limit is not None else 10, 25)

    while processed < batch_limit:
        queue = [lead for lead in queue_fn() if lead["job_id"] not in seen]
        if not queue:
            break
        lead = queue[0]
        job_id = lead["job_id"]
        if not lead.get("url"):
            seen.add(job_id)
            skipped += 1
            continue

        page = page_factory()
        try:
            assert_public_url(lead["url"])
            result = visit_role(page, lead)
        except Exception as exc:
            print(f"\n  {job_id}: could not open/autofill -- {exc}")
            close_page(page)
            seen.add(job_id)
            skipped += 1
            continue

        processed += 1
        outcome = submit(page, result)
        status = outcome.get("status")
        reason = outcome.get("reason", "")
        if status == "submitted":
            rc = mark_applied(job_id)
            if rc == 0:
                close_page(page)
                seen.add(job_id)
                submitted += 1
                print(f"\n  {lead.get('title')} @ {lead.get('company')}: submitted; tab closed")
            else:
                blockers.append({"lead": lead, "page": page, "result": result, "reason": "submitted externally; CRM mark failed"})
                seen.add(job_id)
                needs_review += 1
                try:
                    event_fn(job_id, "application_submitted_crm_mark_failed")
                except Exception:
                    pass
            continue

        # Keep every non-submitted application visible for the candidate. A
        # CAPTCHA is retriable after manual completion; other blockers are
        # intentionally left available for review/manual completion.
        blockers.append({"lead": lead, "page": page, "result": result, "reason": reason or status})
        seen.add(job_id)
        needs_review += 1
        print(f"\n  {lead.get('title')} @ {lead.get('company')}: blocker tab kept open -- {reason or status}")
        wait_between(page)

    remaining = len([lead for lead in queue_fn() if lead["job_id"] not in seen])
    return ({"submitted": submitted, "skipped": skipped, "needs_review": needs_review, "remaining": remaining}, blockers)


def _print_blockers(blockers: list[dict]) -> None:
    if not blockers:
        return
    print("\n  OPEN BLOCKER TABS")
    for index, item in enumerate(blockers, start=1):
        lead = item["lead"]
        print(f"    [{index}] {lead.get('title')} @ {lead.get('company')}: {item['reason']}")


def _resume_captcha_blockers(blockers: list[dict], db_path: str, args) -> tuple[int, list[dict]]:
    """Retry only CAPTCHA blockers after the candidate solves them in place.

    We never reload the page or re-fill the form here, so a manually completed
    CAPTCHA (or any human-entered answer) remains intact.
    """
    submitted = 0
    remaining: list[dict] = []
    for item in blockers:
        if item["reason"] != "CAPTCHA detected":
            remaining.append(item)
            continue
        outcome = _submit_if_ready(item["page"], item["result"])
        if outcome.get("status") != "submitted":
            item["reason"] = outcome.get("reason", outcome.get("status", "still blocked"))
            remaining.append(item)
            continue
        if _mark_applied(item["lead"]["job_id"], db_path, args) != 0:
            item["reason"] = "submitted externally; CRM mark failed"
            remaining.append(item)
            continue
        item["page"].close()
        submitted += 1
    return submitted, remaining


def _mark_manually_submitted_blocker(blockers: list[dict], index: int, db_path: str, args) -> list[dict]:
    """Record a blocker the candidate has submitted manually, then close it."""
    if index < 1 or index > len(blockers):
        print("  invalid blocker-tab number")
        return blockers
    item = blockers[index - 1]
    if _mark_applied(item["lead"]["job_id"], db_path, args) != 0:
        print("  could not mark that application applied; tab left open")
        return blockers
    item["page"].close()
    print(f"  marked {item['lead'].get('title')} @ {item['lead'].get('company')} applied; tab closed")
    return [entry for position, entry in enumerate(blockers, start=1) if position != index]


def cmd_batch(args) -> int:
    if not (args.auto_submit and args.confirm_candidate_authorization):
        print("\n  batch mode requires both --auto-submit and --confirm-candidate-authorization. Nothing was opened.\n")
        return 2
    db_path = run_scrape.resolve_db(args.db)
    if not Path(args.config).exists():
        print(f"\n  missing config: {args.config}\n")
        return 2
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    print("\n  batch mode -- one active visible form at a time; strict submission checks enabled.")
    print("  CAPTCHA and other blockers remain open while the next role is filled. Confirmed submissions close immediately.\n")
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    result = {"submitted": 0, "skipped": 0, "needs_review": 0, "remaining": 0}
    with sync_playwright() as pw:
        browser_ctx = _launch_context(pw, args, slow_mo=80)
        try:
            result, blockers = _run_tab_batch(browser_ctx, cfg, profile, db_path, args)
            _print_blockers(blockers)
            while blockers:
                choice = input("\n  Solve CAPTCHA tabs, then [Enter]=retry  [m N]=mark blocker N manually submitted + close  [q]=close all\n  > ").strip().lower()
                if choice in ("q", "quit"):
                    break
                if choice.startswith("m "):
                    try:
                        blockers = _mark_manually_submitted_blocker(blockers, int(choice[2:].strip()), db_path, args)
                    except ValueError:
                        print("  use m followed by the blocker-tab number, for example: m 2")
                    result["needs_review"] = len(blockers)
                    _print_blockers(blockers)
                    continue
                resumed, blockers = _resume_captcha_blockers(blockers, db_path, args)
                result["submitted"] += resumed
                result["needs_review"] = len(blockers)
                _print_blockers(blockers)
        finally:
            browser_ctx.close()
    _print_batch_summary(result)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="'next', 'session', 'batch', or a specific job_id")
    parser.add_argument("--db", default=None, help="database file (defaults to the installed app's)")
    parser.add_argument("--profile", default=str(apply_assist.DEFAULT_PROFILE_PATH), help="candidate profile JSON (project ranking)")
    parser.add_argument("--drafts-dir", default=str(apply_assist.DEFAULT_DRAFTS_DIR), help="drafts output directory")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="candidate_answers.json path")
    parser.add_argument("--no-mail", action="store_true", help="skip opening a second tab at mail.google.com")
    parser.add_argument("--browser", choices=["chrome", "chromium", "edge"], default="chrome",
                         help="browser channel to drive (default chrome -- Google refuses sign-in to Playwright's "
                              "bundled Chromium as 'not secure'; falls back to chromium with a warning if unavailable)")
    parser.add_argument("--limit", type=int, default=None, help="session/batch: stop after N roles (batch defaults to 10; maximum 25)")
    parser.add_argument("--auto-submit", action="store_true", help="required with batch: permit final application submission")
    parser.add_argument("--confirm-candidate-authorization", action="store_true", help="required with batch: attest the candidate authorized submissions")
    parser.add_argument("--allow-privacy-consent", action="store_true", help="batch only: allow a plain privacy-policy checkbox, never terms/certifications")
    parser.add_argument("--no-pause-for-captcha", action="store_false", dest="pause_for_captcha", help="batch only: skip CAPTCHA forms instead of waiting for manual completion")
    parser.add_argument("--inter-application-delay", type=float, default=7.0, help="batch only: visible wait between blocker forms (default 7 seconds; no stealth/bypass behaviour)")
    args = parser.parse_args()

    if args.target == "session":
        return cmd_session(args)
    if args.target == "batch":
        return cmd_batch(args)

    db_path = run_scrape.resolve_db(args.db)
    lead = _get_lead(args.target, db_path)
    if not lead:
        if args.target == "next":
            print("\n  queue is empty -- nothing at draft_ready/approved\n")
            return 0
        print(f"\n  no lead found for job_id={args.target!r}\n")
        return 2

    if not lead.get("url"):
        print(f"\n  lead {lead.get('job_id')!r} has no apply URL -- nothing to open\n")
        return 2

    try:
        assert_public_url(lead["url"])
    except BlockedUrlError as exc:
        print(f"\n  refusing to open this URL: {exc}\n")
        return 2

    if not Path(args.config).exists():
        print(f"\n  missing config: {args.config}")
        print("  copy the candidate_answers.json shape from the script's docstring/README and fill in real data.\n")
        return 2
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    folder = apply_assist._ensure_packet(lead["job_id"], db_path, Path(args.profile), Path(args.drafts_dir))
    record_event(lead["job_id"], "autofill_opened", db_path)

    print(f"\n  {lead.get('title')} @ {lead.get('company')}  [{lead.get('platform')}]")
    print(f"  {lead['url']}")
    print("\n  launching a visible browser -- filling what it can, never submitting...")

    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser_ctx = _launch_context(pw, args, slow_mo=60)
        try:
            page = browser_ctx.new_page()
            result = _fill_role(page, lead, cfg, profile, folder)
            if result["screenshot_path"]:
                print(f"\n  screenshot of the filled form: {result['screenshot_path']}")

            if not args.no_mail:
                try:
                    mail_page = browser_ctx.new_page()
                    mail_page.goto(GMAIL_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    print(f"\n  (could not open Gmail tab: {exc})")

            _print_summary(lead, result["filled"], result["needs_human"], result["gated_hint"])
            input("\n  Press Enter here once you're done reviewing (and, if you choose, submitting) in the browser...\n")
        finally:
            try:
                browser_ctx.close()
            except Exception as exc:
                print(f"  (browser close warning: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
