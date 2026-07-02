"""An explicit min-signal-score of 0 means "accept everything" and must be honoured.

0 is a valid user choice (the number input's min bound is 0), NOT a sentinel for
"unset". Two spots used a falsy `or default` idiom that silently overrode 0 with the
default: x_scout._int_setting and quality_gate.evaluate_lead_quality (the latter
also defeated free_scout's own explicit-0 handling, which passes min_quality=0).
"""

from __future__ import annotations

import pytest

from automation.x_scout import _int_setting
from discovery.quality_gate import MIN_DEFAULT_QUALITY, evaluate_lead_quality


@pytest.mark.parametrize("value,expected", [
    (0, 0),        # explicit accept-all — must survive, not become the default
    ("0", 0),
    (None, 55),    # genuinely unset -> default
    ("", 55),      # blank -> default
    ("  ", 55),
    ("30", 30),
    (30, 30),
    ("abc", 55),   # non-numeric -> default
    (150, 100),    # clamp to max
    (-5, 0),       # clamp to min
])
def test_int_setting_distinguishes_explicit_zero_from_unset(value, expected):
    assert _int_setting(value, 55, 0, 100) == expected


def _clean_lead(signal_score: int) -> dict:
    # _fresh_source marks the lead recent (no staleness penalty), so the final score
    # equals signal_score and the threshold comparison is the only thing under test.
    return {
        "url": "https://example.com/jobs/1",
        "company": "Acme AI",
        "title": "Backend Engineer",
        "description": "Build reliable Python services and data pipelines. " * 5,
        "signal_score": signal_score,
        "_fresh_source": "google_past_week",
    }


def test_quality_gate_honors_explicit_zero_min_quality():
    # score <= signal_score (30) < MIN_DEFAULT_QUALITY (60): rejected at the default
    # threshold but accepted when the user explicitly asks for 0 ("accept all").
    lead = _clean_lead(30)
    assert evaluate_lead_quality(lead, min_quality=0)["accepted"] is True
    assert evaluate_lead_quality(lead, min_quality=MIN_DEFAULT_QUALITY)["accepted"] is False


def test_quality_gate_still_enforces_a_nonzero_threshold():
    lead = _clean_lead(40)
    assert evaluate_lead_quality(lead, min_quality=50)["accepted"] is False
    assert evaluate_lead_quality(lead, min_quality=20)["accepted"] is True
