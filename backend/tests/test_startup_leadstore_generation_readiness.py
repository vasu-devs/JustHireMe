from __future__ import annotations

from types import SimpleNamespace


def _repo_with_settings(values: dict[str, str]):
    return SimpleNamespace(settings=SimpleNamespace(get_settings=lambda: values))


def test_startup_validation_reports_actionable_configuration_warnings(monkeypatch):
    from api.startup_validation import startup_warnings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)

    warnings = startup_warnings(_repo_with_settings({
        "x_enabled": "true",
        "custom_connectors_enabled": "true",
        "custom_connectors": " ",
        "llm_provider": "openai",
        "job_boards": "example",
    }))

    assert "X scanning is enabled but x_bearer_token is missing." in warnings
    assert "Custom connectors are enabled but custom_connectors is empty." in warnings
    assert "LLM provider 'openai' is selected but no API key is configured." in warnings
    assert "Job target may be invalid or too broad: example" in warnings


def test_startup_validation_warns_when_free_sources_have_no_targets():
    from api.startup_validation import startup_warnings

    warnings = startup_warnings(_repo_with_settings({
        "free_sources_enabled": "true",
        "free_source_targets": "",
        "job_boards": "",
    }))

    assert warnings == [
        "Free-source scanning is enabled but no free source targets or job boards are configured.",
    ]


def test_startup_validation_logs_every_warning(monkeypatch):
    from api.startup_validation import log_startup_warnings

    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    logged: list[str] = []
    logger = SimpleNamespace(warning=lambda _template, warning: logged.append(warning))

    warnings = log_startup_warnings(_repo_with_settings({"x_enabled": "true"}), logger)

    assert logged == warnings
    assert logged == ["X scanning is enabled but x_bearer_token is missing."]


def test_save_lead_compat_maps_legacy_arguments_to_repository_payload(monkeypatch):
    from automation import lead_store

    saved: dict = {}

    class Leads:
        def save_lead(self, lead: dict) -> None:
            saved.update(lead)

    monkeypatch.setattr(lead_store, "create_repository", lambda: SimpleNamespace(leads=Leads()))

    lead_store.save_lead_compat(
        "job-1",
        "Applied AI Engineer",
        "Acme",
        "https://example.com/jobs/1",
        "manual",
        description="Build Python and FastAPI workflow software.",
        signal_score="87",
        signal_tags=["python", "fastapi"],
        fit_bullets="Strong backend fit",
        followup_sequence=["Day 2: follow up"],
        base_signal_score="80",
        learning_delta="7",
        learning_reason="feedback boosted",
        source_meta={"source": "manual"},
    )

    assert saved["job_id"] == "job-1"
    assert saved["kind"] == "job"
    assert saved["signal_score"] == 87
    assert saved["signal_tags"] == ["python", "fastapi"]
    assert saved["fit_bullets"] == "Strong backend fit"
    assert saved["base_signal_score"] == 80
    assert saved["learning_delta"] == 7
    assert saved["learning_reason"] == "feedback boosted"
    assert saved["source_meta"] == {"source": "manual"}


def test_generation_readiness_blocks_url_only_and_thin_leads():
    from core.generation_readiness import lead_generation_blocker

    assert "URL alone" in lead_generation_blocker({
        "title": "https://jobs.example.com/role",
        "description": "",
        "source_meta": {"input_url_only": True},
    })
    assert "only contains a URL" in lead_generation_blocker({
        "title": "https://jobs.example.com/role",
        "description": "https://jobs.example.com/role",
    })
    assert "no role requirements" in lead_generation_blocker({
        "title": "Applied AI Engineer",
        "company": "Acme",
        "description": "",
        "match_points": [],
    })
    assert "fuller job description" in lead_generation_blocker({
        "title": "Ops",
        "company": "Acme",
        "description": "Nice team.",
    })


def test_generation_readiness_allows_substantive_role_context():
    from core.generation_readiness import lead_generation_blocker

    assert lead_generation_blocker({
        "title": "Applied AI Engineer",
        "company": "Acme",
        "description": "Build Python, FastAPI, React, and LLM workflow software for internal automation.",
    }) == ""


def test_generation_readiness_allows_non_tech_roles():
    """A full non-technical description must not be blocked by a tech-keyword
    filter. Regression for issue #92: a 'Financial Aid Advisor' posting has a
    complete description but contains no software/engineering keywords."""
    from core.generation_readiness import lead_generation_blocker

    assert lead_generation_blocker({
        "title": "Advisor Financial Aid",
        "company": "Universal Technical Institute",
        "description": (
            "The Financial Aid Advisor delivers on our commitment of service "
            "excellence by building rapport, delivering clear and accurate "
            "information, offering effective solutions, and maintaining contact "
            "with students about their financial aid options."
        ),
    }) == ""
