"""Discovery source adapters."""

from discovery.sources.ats import (
    scrape_ashby,
    scrape_direct_ats_url,
    scrape_target as scrape_ats_target,
    scrape_greenhouse,
    is_ats_target,
    scrape_lever,
    scrape_workable,
)
from discovery.sources.apify import run_actor as run_apify_actor
from discovery.sources.apify import run_board_scan
from discovery.sources.custom import scrape_custom_connector
from discovery.sources.github_jobs import scrape_github
from discovery.sources.hackernews import scrape_hn, scrape_hn_hiring
from discovery.sources.reddit import scrape_reddit
from discovery.sources.rss import (
    scrape_jobicy_api,
    scrape_remoteok,
    scrape_remotive,
    scrape_rss,
)
from discovery.sources.x_twitter import run_x_scan
from discovery.sources.web import scrape as scrape_web
from discovery.sources.web import scrape_github_jobs_target, scrape_wellfound_target

__all__ = [
    "is_ats_target",
    "run_apify_actor",
    "run_board_scan",
    "run_x_scan",
    "scrape_ashby",
    "scrape_ats_target",
    "scrape_custom_connector",
    "scrape_direct_ats_url",
    "scrape_github",
    "scrape_github_jobs_target",
    "scrape_greenhouse",
    "scrape_hn",
    "scrape_hn_hiring",
    "scrape_jobicy_api",
    "scrape_lever",
    "scrape_reddit",
    "scrape_remoteok",
    "scrape_remotive",
    "scrape_rss",
    "scrape_web",
    "scrape_wellfound_target",
    "scrape_workable",
]
