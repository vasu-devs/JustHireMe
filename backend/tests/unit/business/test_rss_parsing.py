"""discovery/sources/rss.py — the pure parsing half of the RSS/API scrapers.

These functions decide what a job board's payload *means* (which platform, which
company, which role, what the description says). They need no network, and a
mistake here silently mislabels every lead from that source.
"""

from __future__ import annotations

import pytest

from discovery.sources import rss


# ------------------------------------------------------------------- targeting


@pytest.mark.parametrize("url", [
    "https://x.com/jobs.rss", "https://x.com/jobs.xml",
    "https://x.com/rss", "https://x.com/feed", "https://x.com/feed/",
    "https://x.com/feed?utm=1",
])
def test_is_rss_target_accepts_feed_shaped_urls(url):
    assert rss.is_rss_target(url) is True


@pytest.mark.parametrize("url", ["https://x.com/api/jobs", "https://x.com/careers", ""])
def test_is_rss_target_rejects_everything_else(url):
    assert rss.is_rss_target(url) is False


@pytest.mark.parametrize("url, platform", [
    ("https://remoteok.com/api", "remoteok"),
    ("https://remotive.com/api/remote-jobs", "remotive"),
    ("https://jobicy.com/feed/newjobs", "jobicy"),
    ("https://weworkremotely.com/remote-jobs.rss", "weworkremotely"),
    ("https://boards.greenhouse.io/acme", "greenhouse"),
    ("https://jobs.lever.co/acme", "lever"),
    ("https://jobs.ashbyhq.com/acme", "ashby"),
    ("https://apply.workable.com/acme", "workable"),
    ("https://careers.acme.com/jobs", "scout"),
])
def test_platform_is_derived_from_the_host(url, platform):
    assert rss.platform_from_url(url) == platform


def test_platform_lookup_is_case_insensitive():
    assert rss.platform_from_url("https://Boards.Greenhouse.IO/acme") == "greenhouse"


def test_lead_source_prefers_an_explicit_platform():
    assert rss.lead_source({"platform": " RemoteOK ", "url": "https://lever.co/x"}) == "remoteok"


def test_lead_source_falls_back_to_the_url():
    assert rss.lead_source({"url": "https://jobs.lever.co/acme"}) == "lever"
    assert rss.lead_source({}) == "scout"


# ------------------------------------------------------------------ formatting


@pytest.mark.parametrize("value, expected", [
    (None, ""),
    ("  spaced  ", "spaced"),
    (["a", " b ", "", None], "a, b"),
    (("x", "y"), "x, y"),
    (42, "42"),
])
def test_compact_normalises_scalars_and_collections(value, expected):
    assert rss.compact(value) == expected


def test_detail_is_omitted_entirely_when_there_is_no_value():
    assert rss.detail("Salary", "120k") == "Salary: 120k"
    assert rss.detail("Salary", "") == ""
    assert rss.detail("Salary", None) == ""


def test_description_strips_html_and_joins_parts():
    text = rss.description("<p>Build things</p>", "", "<b>Remote</b>")
    assert "<p>" not in text
    assert "Build things" in text and "Remote" in text


def test_description_is_length_capped():
    assert len(rss.description("x" * 5000, limit=100)) <= 100


@pytest.mark.parametrize("low, high, currency, expected", [
    (100, 200, "USD", "USD 100-200"),
    (100, 200, "", "100-200"),
    (100, "", "USD", "USD 100"),
    ("", 200, "", "200"),
    ("", "", "USD", ""),
    (None, None, "", ""),
])
def test_salary_from_bounds(low, high, currency, expected):
    assert rss.salary_from_bounds(low, high, currency) == expected


# --------------------------------------------------------- company / role split


def test_the_at_separator_splits_role_from_company():
    company, role = rss.rss_company_and_role("Senior Engineer at Acme Corp", "scout")
    assert (company, role) == ("Acme Corp", "Senior Engineer")


def test_the_at_split_is_case_insensitive():
    company, role = rss.rss_company_and_role("Nurse AT Mercy Hospital", "scout")
    assert (company, role) == ("Mercy Hospital", "Nurse")


def test_weworkremotely_puts_the_company_first():
    company, role = rss.rss_company_and_role("Acme: Backend Engineer", "weworkremotely")
    assert (company, role) == ("Acme", "Backend Engineer")


def test_a_pipe_separated_title_is_split_role_first_when_it_looks_like_a_role():
    company, role = rss.rss_company_and_role("Backend Engineer | Acme", "scout")
    assert (company, role) == ("Acme", "Backend Engineer")


def test_an_unparseable_title_is_kept_whole_rather_than_guessed():
    company, role = rss.rss_company_and_role("Some entirely opaque headline", "scout")
    assert company == "RSS Feed"
    assert role == "Some entirely opaque headline"


def test_an_empty_title_yields_no_role():
    assert rss.rss_company_and_role("", "scout") == ("RSS Feed", "")


def test_html_is_stripped_before_splitting():
    company, role = rss.rss_company_and_role("<b>Engineer</b> at <i>Acme</i>", "scout")
    assert "<" not in company and "<" not in role


# --------------------------------------------------------------- noise repair


def test_repair_mojibake_fixes_utf8_read_as_latin1():
    assert rss.repair_mojibake("Senior Engineer â€“ Remote") == "Senior Engineer – Remote"


def test_repair_mojibake_leaves_clean_text_alone():
    assert rss.repair_mojibake("Senior Engineer – Remote") == "Senior Engineer – Remote"


def test_remoteok_injection_is_stripped_when_its_markers_are_present():
    text = "Real duties.\nPlease mention the word **BREATHTAKING** and tag RMT0123 when applying."
    cleaned = rss.strip_remoteok_noise(text)
    assert "BREATHTAKING" not in cleaned
    assert "Real duties." in cleaned


def test_an_employer_sentence_that_merely_looks_similar_is_untouched():
    """The strip anchors on RemoteOK's own markers so real instructions survive."""
    text = "Please mention the word banana and include your salary expectations."
    assert rss.strip_remoteok_noise(text) == text


# ------------------------------------------------------------------ xml helpers


def test_feed_entries_reads_both_rss_items_and_atom_entries():
    import defusedxml.ElementTree as ET

    rss_doc = ET.fromstring("<rss><channel><item><title>A</title></item></channel></rss>")
    atom_doc = ET.fromstring(
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title></entry></feed>'
    )
    assert len(rss.feed_entries(rss_doc)) == 1
    assert len(rss.feed_entries(atom_doc)) == 1


def test_xml_text_returns_the_first_matching_tag():
    import defusedxml.ElementTree as ET

    node = ET.fromstring("<item><link>L</link><title>T</title></item>")
    assert rss.xml_text(node, "missing", "title") == "T"
    assert rss.xml_text(node, "nothing") == ""
