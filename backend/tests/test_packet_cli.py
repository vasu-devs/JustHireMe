from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from application_packets import PacketCommandError, generate_application_packet, render_packet_summary
import packet_cli


class MutatingLeads:
    def get_lead_by_id(self, job_id: str) -> dict:
        return {}

    def get_all_leads(self) -> list[dict]:
        return []

    def __getattr__(self, name):
        if name.startswith(("save", "update", "mark", "delete")):
            raise AssertionError(f"dry-run attempted mutation: {name}")
        raise AttributeError(name)


def _repo(lead: dict, profile: dict | None = None):
    leads = MutatingLeads()
    leads.get_lead_by_id = lambda job_id: lead if job_id == lead["job_id"] else {}
    leads.get_all_leads = lambda: [lead]
    return SimpleNamespace(
        leads=leads,
        profile=SimpleNamespace(get_profile=lambda: profile or {"n": "Mike Matican", "skills": [{"n": "Amazon Ads"}]}),
        settings=SimpleNamespace(get_setting=lambda key, default="": default),
    )


def test_generate_application_packet_dry_run_writes_recoverable_artifacts_without_repo_mutation(tmp_path: Path):
    lead = {
        "job_id": "job-123",
        "title": "Amazon PPC Manager",
        "company": "Acme",
        "url": "https://jobs.example/job-123",
        "score": 92,
        "description": "Manage Amazon Ads Sponsored Products and retail media PPC strategy.",
        "match_points": ["Amazon Ads", "PPC"],
    }

    packet = generate_application_packet("job-123", repo=_repo(lead), output_root=tmp_path, dry_run=True)

    assert packet["dry_run"] is True
    assert packet["submitted"] is False
    assert packet["job_id"] == "job-123"
    assert packet["artifacts"]["resume"]["path"].endswith("resume.md")
    assert packet["artifacts"]["cover_note"]["path"].endswith("cover_note.md")
    assert packet["artifacts"]["application_answers"]["path"].endswith("application_answers.json")
    assert packet["artifacts"]["audit_record"]["path"].endswith("audit_record.json")
    assert Path(packet["summary_markdown_path"]).exists()
    assert Path(packet["artifacts"]["audit_record"]["path"]).exists()
    audit = json.loads(Path(packet["artifacts"]["audit_record"]["path"]).read_text())
    assert audit["submitted"] is False
    assert audit["mutation_policy"] == "dry-run: no lead/application mutation; artifacts only"
    assert (tmp_path / "job-123" / "packet_index.json").exists()


def test_generate_application_packet_reuses_existing_assets_when_present(tmp_path: Path):
    resume = tmp_path / "existing_resume.pdf"
    cover = tmp_path / "existing_cover.pdf"
    resume.write_text("resume")
    cover.write_text("cover")
    lead = {
        "job_id": "job-reuse",
        "title": "Amazon Ads Lead",
        "company": "ReuseCo",
        "url": "https://jobs.example/reuse",
        "score": 95,
        "description": "Lead Amazon Ads Sponsored Brands campaigns.",
        "resume_asset": str(resume),
        "cover_letter_asset": str(cover),
    }

    packet = generate_application_packet("job-reuse", repo=_repo(lead), output_root=tmp_path / "packets", dry_run=True)

    assert packet["reused_existing_assets"] is True
    assert packet["artifacts"]["resume"]["path"] == str(resume)
    assert packet["artifacts"]["cover_note"]["path"] == str(cover)


def test_generate_application_packet_regenerates_when_existing_asset_paths_are_stale(tmp_path: Path):
    lead = {
        "job_id": "job-stale",
        "title": "Amazon Ads Lead",
        "company": "StaleCo",
        "url": "https://jobs.example/stale",
        "score": 95,
        "description": "Lead Amazon Ads Sponsored Brands campaigns.",
        "resume_asset": str(tmp_path / "missing_resume.pdf"),
        "cover_letter_asset": str(tmp_path / "missing_cover.pdf"),
    }

    packet = generate_application_packet("job-stale", repo=_repo(lead), output_root=tmp_path / "packets", dry_run=True)

    assert packet["reused_existing_assets"] is False
    assert packet["artifacts"]["resume"]["path"].endswith("resume.md")
    assert Path(packet["artifacts"]["resume"]["path"]).exists()
    assert any("stale" in warning for warning in packet["warnings"])


def test_generate_application_packet_selects_high_score_job(tmp_path: Path):
    low = {"job_id": "low", "title": "Role", "company": "A", "score": 50, "description": "Python engineer role"}
    high = {"job_id": "high", "title": "Amazon PPC", "company": "B", "score": 91, "description": "Amazon Ads PPC role"}
    leads = MutatingLeads()
    leads.get_all_leads = lambda: [low, high]
    leads.get_lead_by_id = lambda job_id: {"low": low, "high": high}.get(job_id, {})
    repo = SimpleNamespace(
        leads=leads,
        profile=SimpleNamespace(get_profile=lambda: {"n": "Mike Matican", "skills": [{"n": "Amazon Ads"}]}),
        settings=SimpleNamespace(get_setting=lambda key, default="": default),
    )

    packet = generate_application_packet(None, repo=repo, output_root=tmp_path, dry_run=True, high_score=True)

    assert packet["job_id"] == "high"


def test_generate_application_packet_rejects_non_dry_run_submit_mode(tmp_path: Path):
    lead = {"job_id": "job-1", "title": "Role", "company": "A", "score": 80, "description": "Python engineer role"}

    with pytest.raises(PacketCommandError, match="external submission is not supported"):
        generate_application_packet("job-1", repo=_repo(lead), output_root=tmp_path, dry_run=False, submit=True)


def test_generate_application_packet_rejects_non_dry_run_without_submit(tmp_path: Path):
    lead = {"job_id": "job-1", "title": "Role", "company": "A", "score": 80, "description": "Python engineer role"}

    with pytest.raises(PacketCommandError, match="safe mode requires --dry-run"):
        generate_application_packet("job-1", repo=_repo(lead), output_root=tmp_path, dry_run=False)


def test_render_packet_summary_is_telegram_todoist_friendly(tmp_path: Path):
    lead = {"job_id": "job-md", "title": "Amazon PPC", "company": "Acme", "score": 90, "description": "Amazon Ads PPC role"}
    packet = generate_application_packet("job-md", repo=_repo(lead), output_root=tmp_path, dry_run=True)

    summary = render_packet_summary(packet)

    assert "# Application packet: Amazon PPC @ Acme" in summary
    assert "- Submitted: no" in summary
    assert "resume" in summary
    assert "audit_record" in summary


def test_packet_cli_outputs_json_for_high_score_dry_run(monkeypatch, capsys, tmp_path: Path):
    packet = {
        "status": "ready",
        "job_id": "high",
        "dry_run": True,
        "submitted": False,
        "lead": {"title": "Amazon PPC", "company": "Acme"},
        "artifacts": {},
    }

    def fake_generate(selector, **kwargs):
        assert selector is None
        assert kwargs["high_score"] is True
        assert kwargs["dry_run"] is True
        assert kwargs["output_root"] == tmp_path
        assert kwargs["submit"] is False
        return packet

    monkeypatch.setattr(packet_cli, "generate_application_packet", fake_generate)

    code = packet_cli.main(["--high-score", "--output-root", str(tmp_path), "--format", "json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == "high"
