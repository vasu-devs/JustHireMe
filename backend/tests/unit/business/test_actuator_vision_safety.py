"""Vision-actuator safety guardrails (Tier-0 security fix 0.1).

The vision fallback executes LLM-proposed pixel coordinates on an untrusted page.
These tests pin the enforcement that it (a) only treats DOM-verified fills as
"ready to submit", and (b) refuses to click submit/pay/authorize controls.
"""
import asyncio

from automation import actuator


# --- _ready_to_submit: vision actions alone must NOT authorize a submit -------

def test_ready_requires_uploaded_identity_and_clean_preflight():
    assert actuator._ready_to_submit({
        "uploaded": True,
        "fields": ["first_name", "last_name", "email"],
        "vision_actions": 0,
        "required_unfilled": [],
        "sensitive_questions": [],
        "page_blockers": [],
    }) is True


def test_ready_false_without_upload():
    assert actuator._ready_to_submit({"uploaded": False, "fields": ["email"]}) is False


def test_vision_actions_alone_do_not_make_ready():
    # Uploaded + only vision actions, no DOM-verified fields -> NOT ready.
    assert actuator._ready_to_submit({"uploaded": True, "fields": [], "vision_actions": 5}) is False


def test_ready_blocks_unknown_required_and_sensitive_questions():
    base = {"uploaded": True, "fields": ["name", "email"], "page_blockers": []}
    assert actuator._ready_to_submit({**base, "required_unfilled": ["Notice period"]}) is False
    assert actuator._ready_to_submit({**base, "sensitive_questions": ["Visa sponsorship"]}) is False
    assert actuator._ready_to_submit({**base, "required_unfilled": [], "sensitive_questions": []}) is True


class _Body:
    def __init__(self, text):
        self.text = text

    async def inner_text(self, timeout):
        return self.text


class _ConfirmationPage:
    def __init__(self, text, url="https://example.test/apply"):
        self.text = text
        self.url = url

    async def wait_for_timeout(self, _delay):
        return None

    def locator(self, _selector):
        return _Body(self.text)


def test_submission_confirmation_must_be_new_positive_evidence():
    page = _ConfirmationPage("Thank you for applying")
    confirmed, _evidence = asyncio.run(actuator._submission_confirmed(
        page, page.url, "Thank you for applying",
    ))
    assert confirmed is False

    confirmed, evidence = asyncio.run(actuator._submission_confirmed(
        page, page.url, "Complete the fields below",
    ))
    assert confirmed is True
    assert "Thank you" in evidence


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


def test_sensitive_question_regex_catches_defaulted_legal_and_eligibility_controls():
    for label in ["Will you require visa sponsorship?", "Gender", "Accept terms", "Expected salary"]:
        assert actuator._SENSITIVE_QUESTION_RE.search(label), label


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
