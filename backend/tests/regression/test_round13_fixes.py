"""Round-13 audit fixes: the fire/preview identity must resolve the website from the
canonical website_url setting, and Retry-After must tolerate the RFC HTTP-date form."""

from __future__ import annotations

import datetime
import email.utils
from types import SimpleNamespace

import pytest

from discovery.sources.common import retry_after_seconds


def test_get_lead_for_fire_resolves_website_from_website_url_setting():
    from automation.service import get_lead_for_fire_sync

    lead = {"job_id": "j1", "title": "Engineer"}
    repo = SimpleNamespace(
        leads=SimpleNamespace(get_lead_for_fire=lambda _jid: (lead, "")),
        profile=SimpleNamespace(get_profile=lambda: {"n": "Ada Lovelace", "s": "", "projects": []}),
        # The Identity form / GitHub ingest persist the portfolio under website_url.
        settings=SimpleNamespace(get_settings=lambda: {"website_url": "https://ada.dev"}),
    )
    result, _path = get_lead_for_fire_sync("j1", repo)
    assert result["website"] == "https://ada.dev"
    assert result["name"] == "Ada Lovelace"


@pytest.mark.parametrize("value,expected", [
    ("30", 30),
    ("0", 1),          # clamped to a 1s floor
    ("9999", 300),     # clamped to a 300s ceiling
    ("", 15),          # unset -> default
    (None, 15),
    ("garbage", 15),   # non-numeric, non-date -> default (must not raise)
])
def test_retry_after_seconds_delay_form(value, expected):
    assert retry_after_seconds(value) == expected


def test_retry_after_seconds_http_date_form_does_not_crash():
    # RFC 7231 allows an HTTP-date; int() alone raised ValueError and defeated the
    # 429 back-off. A future date parses to a clamped positive int; a past date floors.
    future = email.utils.format_datetime(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=45)
    )
    parsed = retry_after_seconds(future)
    assert isinstance(parsed, int) and 1 <= parsed <= 300
    assert retry_after_seconds("Wed, 21 Oct 2000 07:28:00 GMT") == 1
