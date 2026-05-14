import asyncio
from types import SimpleNamespace
from unittest import mock

from discovery.service import DiscoveryService


def test_discovery_service_skips_disabled_free_sources():
    service = DiscoveryService()

    result = asyncio.run(service.scan_free_sources({"free_sources_enabled": "false"}))

    assert result.leads == []
    assert result.usage == {}
    assert result.errors == []


def test_discovery_service_runs_free_sources_with_profile_targets():
    service = DiscoveryService()
    fake_lead = {"title": "Junior Builder", "url": "https://example.com/job"}

    with mock.patch("automation.free_scout.run", return_value=[fake_lead]) as run, \
         mock.patch("automation.free_scout.LAST_USAGE", {"executed": 1}), \
         mock.patch("automation.free_scout.LAST_ERRORS", []):
        result = asyncio.run(service.scan_free_sources(
            {"free_sources_enabled": "true"},
            profile={"s": "Python developer", "skills": [{"n": "FastAPI"}]},
        ))

    assert result.leads == [fake_lead]
    assert result.usage == {"executed": 1}
    assert result.errors == []
    kwargs = run.call_args.kwargs
    assert kwargs["raw_targets"]
    assert kwargs["kind_filter"] == "job"


def test_discovery_service_skips_x_without_token():
    service = DiscoveryService()

    result = asyncio.run(service.scan_x({}))

    assert result.leads == []
    assert result.usage == {}
    assert result.errors == []


def test_discovery_service_runs_x_through_source_adapter():
    service = DiscoveryService()
    fake_lead = {"title": "X hiring post", "url": "https://x.com/i/web/status/1"}

    with mock.patch("discovery.sources.x_twitter.run_x_scan") as scan:
        scan.return_value.leads = [fake_lead]
        scan.return_value.usage = {"executed_queries": 1}
        scan.return_value.errors = []
        result = asyncio.run(service.scan_x({"x_bearer_token": "tok", "x_search_queries": "hiring"}))

    assert result.leads == [fake_lead]
    assert result.usage == {"executed_queries": 1}
    assert result.errors == []
    assert scan.call_args.kwargs["bearer_token"] == "tok"


def test_discovery_service_plans_board_targets():
    service = DiscoveryService()

    with mock.patch("discovery.query_gen.generate", return_value=["site:jobs.example Python"]) as generate:
        result = asyncio.run(service.plan_board_targets({"s": "Python"}, ["site:jobs.example"], "global"))

    assert result == ["site:jobs.example Python"]
    generate.assert_called_once_with({"s": "Python"}, ["site:jobs.example"], "global")


def test_discovery_service_scans_job_boards():
    service = DiscoveryService()
    fake_lead = {"title": "Backend Engineer", "url": "https://example.com/backend"}

    with mock.patch("discovery.sources.apify.run_board_scan") as scan:
        scan.return_value.leads = [fake_lead]
        scan.return_value.usage = {"targets": 1}
        scan.return_value.errors = []
        result = asyncio.run(service.scan_job_boards(["site:jobs.example Python"], {"apify_token": "tok"}))

    assert result.leads == [fake_lead]
    assert result.usage == {"targets": 1}
    scan.assert_called_once_with(["site:jobs.example Python"], {"apify_token": "tok"})


def test_run_scan_continues_when_board_scan_batch_fails():
    from api.routers import discovery

    broadcasts = []

    class Manager:
        async def broadcast(self, payload):
            broadcasts.append(payload)

    class JobStore:
        def create(self, *_args, **_kwargs):
            return SimpleNamespace(job_id="scan-1")

        def update(self, *_args, **_kwargs):
            return None

    repo = SimpleNamespace(
        settings=SimpleNamespace(
            get_settings=lambda: {
                "job_boards": "site:jobs.example\nsite:slow.example",
                "free_sources_enabled": "false",
                "board_scan_batch_size": "1",
            },
            save_settings=lambda _settings: None,
        ),
        profile=SimpleNamespace(get_profile=lambda: {"s": "Python engineer"}),
        leads=SimpleNamespace(get_discovered_leads=lambda: [{
            "job_id": "job-1",
            "title": "Junior AI Engineer",
            "company": "Acme",
            "url": "https://example.com/job",
            "platform": "manual",
            "description": "Python role",
        }], update_lead_score=lambda *_args, **_kwargs: None),
    )
    service = SimpleNamespace(
        scan_x=mock.AsyncMock(return_value=SimpleNamespace(leads=[], usage={}, errors=[])),
        scan_free_sources=mock.AsyncMock(return_value=SimpleNamespace(leads=[], usage={}, errors=[])),
        plan_board_targets=mock.AsyncMock(return_value=["site:jobs.example", "site:slow.example"]),
        scan_job_boards=mock.AsyncMock(side_effect=RuntimeError("discovery service timed out")),
    )
    ranking = SimpleNamespace(evaluate_lead=mock.AsyncMock(return_value={
        "score": 82,
        "reason": "good match",
        "match_points": [],
        "gaps": [],
    }))

    with mock.patch.object(discovery, "get_job_runner", return_value=JobStore()):
        asyncio.run(discovery.run_scan(
            Manager(),
            repo=repo,
            discovery_service=service,
            ranking_service=ranking,
        ))

    assert ranking.evaluate_lead.await_count == 1
    messages = [payload["msg"] for payload in broadcasts if payload.get("event") in {"scout_source_detail", "eval_done"}]
    assert any("discovery service timed out" in msg for msg in messages)
    assert messages[-1] == "Evaluation cycle complete"


def test_cleanup_bad_leads_skips_already_discarded_rows():
    from data.sqlite.leads import cleanup_bad_leads

    queries = []

    class Cursor:
        def fetchall(self):
            return []

    class Conn:
        def execute(self, query, *_args):
            queries.append(query)
            return Cursor()

        def commit(self):
            return None

        def close(self):
            return None

    with mock.patch("data.sqlite.leads.connect", return_value=Conn()):
        cleanup_bad_leads()

    cleanup_query = queries[0]
    assert "status NOT IN" in cleanup_query
    assert "'discarded'" in cleanup_query
