"""Vision-actuator safety guardrails (Tier-0 security fix 0.1).

The vision fallback executes LLM-proposed pixel coordinates on an untrusted page.
These tests pin the enforcement that it (a) only treats DOM-verified fills as
"ready to submit", and (b) refuses to click submit/pay/authorize controls.
"""
import asyncio

from automation import actuator


# --- _ready_to_submit: vision actions alone must NOT authorize a submit -------

def test_ready_requires_uploaded_and_dom_fields():
    assert actuator._ready_to_submit({"uploaded": True, "fields": ["email"], "vision_actions": 0}) is True


def test_ready_false_without_upload():
    assert actuator._ready_to_submit({"uploaded": False, "fields": ["email"]}) is False


def test_vision_actions_alone_do_not_make_ready():
    # Uploaded + only vision actions, no DOM-verified fields -> NOT ready.
    assert actuator._ready_to_submit({"uploaded": True, "fields": [], "vision_actions": 5}) is False


# --- _clamp -------------------------------------------------------------------

def test_clamp_bounds():
    assert actuator._clamp(-10, 0, 100) == 0
    assert actuator._clamp(500, 0, 100) == 100
    assert actuator._clamp(50, 0, 100) == 50


# --- _DANGEROUS_CLICK_RE ------------------------------------------------------

def test_dangerous_regex_matches_submit_pay():
    for label in ["Submit Application", "Apply now", "Pay $50", "Checkout",
                  "Authorize", "Confirm and continue", "Place order", "Subscribe"]:
        assert actuator._DANGEROUS_CLICK_RE.search(label), label


def test_dangerous_regex_allows_benign_field_labels():
    for label in ["Email address", "First name", "Phone", "Upload resume", "LinkedIn URL"]:
        assert not actuator._DANGEROUS_CLICK_RE.search(label), label


# --- _safe_to_click: default-deny hit-test ------------------------------------

class _FakePage:
    """Minimal page whose evaluate() returns a preset hit-test result (or raises)."""
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise = raise_exc

    async def evaluate(self, _js, _arg):
        if self._raise:
            raise self._raise
        return self._result


def _safe(result=None, raise_exc=None):
    page = _FakePage(result=result, raise_exc=raise_exc)
    return asyncio.run(actuator._safe_to_click(page, 10, 10))


def test_safe_click_blocks_submit_type():
    assert _safe({"found": True, "type": "submit", "text": "Go"}) is False


def test_safe_click_blocks_dangerous_text():
    assert _safe({"found": True, "type": "", "text": "Apply Now"}) is False


def test_safe_click_allows_plain_input():
    assert _safe({"found": True, "type": "text", "text": "Email"}) is True


def test_safe_click_denies_when_no_element():
    assert _safe({"found": False}) is False


def test_safe_click_denies_on_evaluate_error():
    assert _safe(raise_exc=RuntimeError("boom")) is False
