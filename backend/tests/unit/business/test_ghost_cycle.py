"""automation/ghost.py — the unattended scan → score → generate → apply cycle.

Ghost mode runs with nobody watching, so the guards matter more than the happy
path: it must refuse to start when it isn't configured, must not overwrite a
status the user changed mid-cycle, and must cap how many LLM calls it makes.
"""

from __future__ import annotations

import types

import pytest

from automation import ghost


def _cfg(**kw):
    base = {"ghost_mode": "true", "job_boards": "https://boards.example/api"}
    base.update(kw)
    return base


def _manager():
    sent: list[dict] = []

    class Manager:
        async def broadcast(self, message):
            sent.append(message)

    manager = Manager()
    manager.sent = sent
    return manager


def _jobs():
    updates: list[dict] = []

    class Jobs:
        def create(self, *_a, **_k):
            return types.SimpleNamespace(job_id="ghost-1")

        def update(self, _job_id, **kw):
            updates.append(kw)

    jobs = Jobs()
    jobs.updates = updates
    return jobs


def _repo(cfg, profile=None, discovered=None):
    state = {"scores": []}

    class Settings:
        def get_settings(self):
            return dict(cfg)

        def get_setting(self, key, default=""):
            return cfg.get(key, default)

    class Profile:
        def get_profile(self):
            return profile if profile is not None else {"n": "Ada", "skills": [{"n": "Python"}]}

    class Leads:
        def get_discovered_leads(self):
            return list(discovered or [])

        def update_lead_score(self, job_id, score, reason, points, gaps, preserve_status=False, scored_by=""):
            state["scores"].append({"job_id": job_id, "score": score, "preserve_status": preserve_status})

    repo = types.SimpleNamespace(settings=Settings(), profile=Profile(), leads=Leads())
    repo._state = state
    return repo


def _install(monkeypatch, *, repo, jobs, discovery=None, ranking=None, generation=None, automation=None):
    monkeypatch.setattr(ghost, "_default_repo", lambda: repo)
    monkeypatch.setattr(ghost, "get_job_store", lambda: jobs)
    monkeypatch.setattr(ghost, "_default_discovery_service", lambda: discovery or object())
    monkeypatch.setattr(ghost, "_default_ranking_service", lambda: ranking or object())
    monkeypatch.setattr(ghost, "_default_generation_service", lambda: generation or object())
    monkeypatch.setattr(ghost, "_default_automation_service", lambda _repo: automation or object())
    # Keep the cycle off the network unless a test opts in.
    monkeypatch.setattr(ghost, "run_x_signal_scan", _noop)
    monkeypatch.setattr(ghost, "run_free_source_scan", _noop)


async def _noop(*_a, **_k):
    return [], {}, []


# ------------------------------------------------------------------- guards


@pytest.mark.asyncio
async def test_the_cycle_does_nothing_when_ghost_mode_is_off(monkeypatch):
    repo, jobs, manager = _repo(_cfg(ghost_mode="false")), _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs)

    await ghost.create_ghost_tick(manager)()

    assert manager.sent == [], "an unattended cycle must stay silent when disabled"
    assert jobs.updates == [], "and must not even open a job"


@pytest.mark.asyncio
async def test_the_cycle_cancels_when_there_is_nothing_to_search_with(monkeypatch):
    """No profile signal and no explicit targets means every query would be a guess."""
    repo = _repo(_cfg(job_boards=""), profile={})
    jobs, manager = _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs)

    await ghost.create_ghost_tick(manager)()

    assert any(m.get("event") == "ghost_warn" for m in manager.sent)
    assert jobs.updates[-1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_the_cycle_cancels_when_no_source_is_configured(monkeypatch):
    # A blank job_boards setting still resolves to the built-in default targets,
    # so the "no source at all" state has to be forced to reach the guard.
    repo = _repo(_cfg(job_boards=""))
    jobs, manager = _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs)
    monkeypatch.setattr(ghost, "job_targets", lambda *_a, **_k: [])
    monkeypatch.setattr(ghost, "has_x_token", lambda _cfg: False)
    monkeypatch.setattr(ghost, "free_sources_enabled", lambda _cfg: False)

    await ghost.create_ghost_tick(manager)()

    assert jobs.updates[-1]["status"] == "cancelled"
    assert any("no job boards" in str(m.get("msg", "")) for m in manager.sent)


@pytest.mark.asyncio
async def test_a_failing_scout_fails_the_job_instead_of_raising(monkeypatch):
    class Discovery:
        async def plan_board_targets(self, *_a):
            raise RuntimeError("network down")

    repo, jobs, manager = _repo(_cfg()), _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs, discovery=Discovery())

    await ghost.create_ghost_tick(manager)()   # must not raise

    assert jobs.updates[-1]["status"] == "failed"
    assert any(m.get("event") == "ghost_error" for m in manager.sent)


# ------------------------------------------------------------------ scoring


def _discovery(leads=()):
    class Discovery:
        async def plan_board_targets(self, _profile, boards, _focus):
            return boards

        async def scan_job_boards(self, _boards, _cfg):
            return types.SimpleNamespace(leads=list(leads))

    return Discovery()


def _ranking(scores, llm_ids=()):
    seen = {"max_llm": None, "used_llm": []}

    class Ranking:
        async def select_llm_eval_ids(self, _leads, _profile, max_llm=None):
            seen["max_llm"] = max_llm
            return set(llm_ids)

        async def evaluate_lead(self, lead, _profile, _cfg, use_llm=False):
            seen["used_llm"].append((lead["job_id"], use_llm))
            return {"score": scores.get(lead["job_id"], 10), "reason": "r",
                    "match_points": [], "gaps": [], "scored_by": "test"}

    ranking = Ranking()
    ranking.seen = seen
    return ranking


@pytest.mark.asyncio
async def test_background_scoring_never_overwrites_a_user_changed_status(monkeypatch):
    """The eval loop is slow; a user may approve a lead while it runs."""
    discovered = [{"job_id": "a", "title": "A"}, {"job_id": "b", "title": "B"}]
    repo = _repo(_cfg(), discovered=discovered)
    jobs, manager = _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs,
             discovery=_discovery(), ranking=_ranking({"a": 20, "b": 30}))

    await ghost.create_ghost_tick(manager)()

    assert repo._state["scores"], "leads should have been scored"
    assert all(entry["preserve_status"] for entry in repo._state["scores"])


@pytest.mark.asyncio
async def test_the_llm_budget_is_capped_for_an_unattended_run(monkeypatch):
    """Otherwise a background cycle quietly burns tokens on the whole backlog."""
    repo = _repo(_cfg(ghost_max_llm_evaluations="3"), discovered=[{"job_id": "a"}])
    ranking = _ranking({"a": 10})
    _install(monkeypatch, repo=repo, jobs=_jobs(), discovery=_discovery(), ranking=ranking)

    await ghost.create_ghost_tick(_manager())()

    assert ranking.seen["max_llm"] == 3


@pytest.mark.asyncio
async def test_only_the_selected_leads_are_evaluated_with_the_llm(monkeypatch):
    discovered = [{"job_id": "a"}, {"job_id": "b"}]
    repo = _repo(_cfg(), discovered=discovered)
    ranking = _ranking({"a": 10, "b": 10}, llm_ids={"a"})
    _install(monkeypatch, repo=repo, jobs=_jobs(), discovery=_discovery(), ranking=ranking)

    await ghost.create_ghost_tick(_manager())()

    assert dict(ranking.seen["used_llm"]) == {"a": True, "b": False}


@pytest.mark.asyncio
async def test_a_lead_that_fails_evaluation_does_not_stop_the_cycle(monkeypatch):
    class Ranking:
        async def select_llm_eval_ids(self, *_a, **_k):
            return set()

        async def evaluate_lead(self, lead, *_a, **_k):
            if lead["job_id"] == "a":
                raise RuntimeError("scorer blew up")
            return {"score": 10, "reason": "r", "match_points": [], "gaps": [], "scored_by": "t"}

    repo = _repo(_cfg(), discovered=[{"job_id": "a"}, {"job_id": "b"}])
    jobs, manager = _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs, discovery=_discovery(), ranking=Ranking())

    await ghost.create_ghost_tick(manager)()

    assert [entry["job_id"] for entry in repo._state["scores"]] == ["b"]
    assert jobs.updates[-1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_a_complete_cycle_reports_success(monkeypatch):
    repo = _repo(_cfg(), discovered=[])
    jobs, manager = _jobs(), _manager()
    _install(monkeypatch, repo=repo, jobs=jobs, discovery=_discovery(), ranking=_ranking({}))

    await ghost.create_ghost_tick(manager)()

    assert any(m.get("event") == "ghost_done" for m in manager.sent)
    assert jobs.updates[-1]["status"] == "succeeded"
