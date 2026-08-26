from __future__ import annotations

import asyncio
from types import SimpleNamespace

from automation.service import AutomationService


def test_automation_service_reads_fire_lead_from_repository():
    calls: list[str] = []

    repo = SimpleNamespace(
        leads=SimpleNamespace(
            get_lead_for_fire=lambda job_id: calls.append(job_id) or ({"job_id": job_id}, "resume.pdf"),
            mark_applied=lambda job_id: calls.append(f"applied:{job_id}"),
        ),
        settings=SimpleNamespace(save_settings=lambda settings: None),
    )

    service = AutomationService(repo=repo)

    lead, asset = asyncio.run(service.get_lead_for_fire("job-1"))
    asyncio.run(service.mark_applied("job-1"))

    assert lead == {"job_id": "job-1"}
    assert asset == "resume.pdf"
    assert calls == ["job-1", "applied:job-1"]
