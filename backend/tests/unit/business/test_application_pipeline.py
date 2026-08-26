from __future__ import annotations

import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[3]
SCRIPTS = BACKEND / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import application_pipeline as pipeline  # noqa: E402


def test_load_targets_supports_csv_and_deduplicates_urls(tmp_path):
    source = tmp_path / "targets.csv"
    source.write_text(
        "url,title,company,score\n"
        "https://jobs.example.com/role#details,AI Engineer,Example,91\n"
        "https://jobs.example.com/role,Duplicate,Example,10\n",
        encoding="utf-8",
    )

    assert pipeline.load_targets(source) == [{
        "url": "https://jobs.example.com/role", "title": "AI Engineer", "company": "Example",
        "location": "", "description": "", "score": 91, "source": "targets.csv",
    }]


def test_load_targets_supports_url_text_and_skips_comments(tmp_path):
    source = tmp_path / "targets.txt"
    source.write_text("# ranked links\nhttps://jobs.ashbyhq.com/acme/abc\n\n", encoding="utf-8")
    assert pipeline.load_targets(source)[0]["url"] == "https://jobs.ashbyhq.com/acme/abc"


def test_lead_from_target_has_stable_id_and_platform():
    target = {"url": "https://jobs.ashbyhq.com/acme/abc", "title": "Applied AI Engineer", "company": "Acme",
              "location": "Remote", "description": "Build agent systems.", "score": 80, "source": "input.json"}
    lead = pipeline._lead_from_target(target)
    assert lead["job_id"] == pipeline.intake_job_id(target["url"])
    assert lead["platform"] == "ashby"
    assert lead["source_meta"]["intake"] is True


def test_normalize_url_rejects_non_web_targets():
    try:
        pipeline.normalize_url("mailto:jobs@example.com")
    except ValueError as exc:
        assert "http(s)" in str(exc)
    else:
        raise AssertionError("non-web target must be rejected")
