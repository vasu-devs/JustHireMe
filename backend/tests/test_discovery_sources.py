import asyncio
from typing import ClassVar
from unittest import mock

from discovery.sources import rss
from discovery.sources import hackernews
from discovery.sources import ats
from discovery.sources import apify
from discovery.sources import web


def test_rss_target_detection():
    assert rss.is_rss_target("https://weworkremotely.com/remote-jobs.rss")
    assert rss.is_rss_target("https://example.com/feed")
    assert not rss.is_rss_target("https://weworkremotely.com/categories/remote-programming-jobs")


def test_rss_company_and_role_parses_common_titles():
    assert rss.rss_company_and_role("Backend Engineer at Acme", "rss") == ("Acme", "Backend Engineer")
    assert rss.rss_company_and_role("Acme: Frontend Developer", "weworkremotely") == ("Acme", "Frontend Developer")


def test_rss_description_strips_html_and_details():
    desc = rss.description("<p>Build APIs</p>", rss.detail("Location", "Remote"))

    assert "Build APIs" in desc
    assert "Location: Remote" in desc
    assert "<p>" not in desc


def test_hackernews_hiring_story_detection():
    assert hackernews.is_hn_hiring_story({"title": "Ask HN: Who is hiring? (April 2026)"})
    assert not hackernews.is_hn_hiring_story({"title": "Ask HN: Who wants to be hired?"})


def test_hackernews_company_role_parsing():
    text = "Acme AI | Backend Engineer | Remote | Python, FastAPI\nWe are hiring for platform work."

    assert hackernews.looks_like_hn_job_post(text)
    assert hackernews.hn_company_role(text) == ("Acme AI", "Backend Engineer")
    assert hackernews.strip_html_text("Claude code&#x2F;anthropic") == "Claude code/anthropic"


def test_web_source_target_helpers():
    assert web.ensure_scheme("example.com/jobs") == "https://example.com/jobs"
    assert web.ensure_scheme("site:jobs.example.com") == "site:jobs.example.com"
    assert web.google_past_week_url("site:jobs.example.com Python jobs") == (
        "https://www.google.com/search?q=site:jobs.example.com+Python+jobs&tbs=qdr:w"
    )


def test_web_source_github_jobs_marks_platform():
    with mock.patch("discovery.sources.web.scrape", return_value=[{"platform": "scout"}]):
        leads = web.scrape_github_jobs_target("https://github.com/example/jobs")

    assert leads[0]["platform"] == "github_jobs"


def test_ats_target_detection():
    assert ats.is_ats_target("ats:greenhouse:openai")
    assert ats.is_ats_target("https://jobs.ashbyhq.com/example")
    assert not ats.is_ats_target("https://example.com/jobs")


def test_ats_target_dispatches_provider():
    async def run():
        with mock.patch("discovery.sources.ats.scrape_greenhouse", return_value=[]) as scrape:
            await ats.scrape_target("ats:greenhouse:openai")
        scrape.assert_called_once_with("openai")

    asyncio.run(run())


def test_apify_actor_posts_to_dataset_endpoint():
    class FakeResponse:
        status_code = 200
        headers: ClassVar[dict] = {}

        def raise_for_status(self):
            return None

        def json(self):
            return [{"title": "Role"}]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, params=None, json=None):
            self.calls.append((url, params, json))
            return FakeResponse()

    async def run():
        with mock.patch("discovery.sources.apify.httpx.AsyncClient", FakeClient):
            return await apify.run_actor("owner/actor", {"queries": ["python"]}, "token")

    assert asyncio.run(run()) == [{"title": "Role"}]
