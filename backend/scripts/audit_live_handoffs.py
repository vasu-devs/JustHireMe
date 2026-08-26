"""Verify that indexed application handoffs still expose the exact live role."""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opportunities.models import SourceRecord
from data.sqlite import connection as sqlite_connection

# A legacy graph test temporarily shadows sys.modules["sqlite3"] during full
# collection. Reuse the data layer's stable stdlib handle so suite order cannot
# change this audit helper's connector.
sqlite3 = sqlite_connection.sqlite3


_APPLY_CONTROL = re.compile(
    r"mailto:|\bapply now\b|\bapply for this job\b|\bsubmit application\b",
    re.I,
)
_UNAVAILABLE = re.compile(
    r"\b(job|position|role)\s+(?:is\s+)?no longer available\b|"
    r"\bposition has been filled\b|\bno longer accepting applications\b|"
    r"\bpage not found\b",
    re.I,
)


def assess_handoff(
    *,
    title: str,
    response_html: str,
    status_code: int,
    application_available: bool = False,
) -> dict:
    visible = html.unescape(response_html)
    # Provider HTML frequently contains formatting-only duplicate whitespace
    # inside a title (AICTE currently renders ``WEB /  APP``). Canonical parsing
    # collapses it, so the live verifier must compare the same normalized text
    # while still requiring the complete title in order.
    normalized_page = re.sub(r"\s+", " ", visible).casefold()
    normalized_title = re.sub(r"\s+", " ", html.unescape(title)).strip().casefold()
    return {
        "http_status": status_code,
        "exact_title_present": bool(normalized_title and normalized_title in normalized_page),
        "apply_control_present": application_available or bool(_APPLY_CONTROL.search(visible)),
        "unavailable_marker_present": bool(_UNAVAILABLE.search(visible)),
    }


def authoritative_application_available(
    record: SourceRecord,
    *,
    live_payload: dict | None = None,
) -> bool:
    """Return provider-owned evidence for application controls hydrated by JS."""
    if record.provider == "workday":
        return (
            record.public_metadata.get("can_apply") is True
            and record.public_metadata.get("posted") is True
        )
    if record.provider == "ashby":
        return (
            record.public_metadata.get("is_listed") is True
            and record.public_metadata.get("apply_url") == record.apply_url
        )
    if record.provider == "smartrecruiters":
        payload = live_payload or record.public_metadata
        return (
            payload.get("active") is not False
            and bool(payload.get("applyUrl") or payload.get("apply_url"))
        )
    return False


def _latest_records(
    db_path: Path,
    provider: str,
    *,
    target_ids: list[str] | None = None,
) -> list[SourceRecord]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        normalized_targets = sorted({
            value.strip().lower() for value in (target_ids or []) if value.strip()
        })
        target_clause = ""
        parameters: list[str] = [provider]
        if normalized_targets:
            placeholders = ",".join("?" for _ in normalized_targets)
            target_clause = f" AND lower(source_target_id) IN ({placeholders})"
            parameters.extend(normalized_targets)
        rows = connection.execute(
            f"""
            WITH latest AS (
                SELECT payload_json,
                       ROW_NUMBER() OVER (
                           -- The requisition ID itself can be newly populated by
                           -- a parser upgrade. URL is the stable handoff identity
                           -- for selecting the latest observation here.
                           PARTITION BY provider_tenant,canonical_source_url
                           ORDER BY observed_at DESC,source_record_id DESC
                       ) AS position
                FROM opportunity_source_records
                WHERE provider=?
                  {target_clause}
            )
            SELECT payload_json FROM latest WHERE position=1
            """,
            parameters,
        ).fetchall()
    finally:
        connection.close()
    return [SourceRecord.model_validate_json(row["payload_json"]) for row in rows]


async def _audit(records: list[SourceRecord]) -> list[dict]:
    semaphore = asyncio.Semaphore(4)
    headers = {"User-Agent": "JustHireMe live application handoff audit"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        async def check(record: SourceRecord) -> dict:
            try:
                request_url = record.apply_url
                if record.provider == "smartrecruiters":
                    request_url = str(record.public_metadata.get("api_ref") or request_url)
                response = None
                for attempt in range(3):
                    async with semaphore:
                        response = await client.get(request_url)
                    if "community.workday.com/maintenance-page" not in str(response.url):
                        break
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt)
                assert response is not None
                live_payload = None
                if record.provider == "smartrecruiters":
                    try:
                        candidate_payload = response.json()
                    except ValueError:
                        candidate_payload = None
                    if isinstance(candidate_payload, dict):
                        live_payload = candidate_payload
                result = assess_handoff(
                    title=record.title,
                    response_html=response.text,
                    status_code=response.status_code,
                    # Workday and Ashby can hydrate application controls
                    # client-side. Their public posting APIs supply the
                    # authoritative current-list/application evidence.
                    application_available=authoritative_application_available(
                        record,
                        live_payload=live_payload,
                    ),
                )
                result["final_url"] = str(response.url)
            except Exception as exc:
                result = {
                    "http_status": 0,
                    "exact_title_present": False,
                    "apply_control_present": False,
                    "unavailable_marker_present": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "final_url": "",
                }
            return {
                "provider_requisition_id": record.provider_requisition_id,
                "title": record.title,
                "apply_url": record.apply_url,
                **result,
            }

        return list(await asyncio.gather(*(check(record) for record in records)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument(
        "--target-id",
        action="append",
        help="Optional exact source target ID; repeat to audit selected targets only",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    records = _latest_records(
        args.db_path.expanduser().resolve(),
        args.provider.strip().lower(),
        target_ids=args.target_id,
    )
    rows = asyncio.run(_audit(records))
    failures = [
        row
        for row in rows
        if row["http_status"] != 200
        or not row["exact_title_present"]
        or not row["apply_control_present"]
        or row["unavailable_marker_present"]
    ]
    report = {
        "provider": args.provider.strip().lower(),
        "target_ids": sorted({
            value.strip().lower() for value in (args.target_id or []) if value.strip()
        }),
        "checked": len(rows),
        "live": len(rows) - len(failures),
        "failures": failures,
        "rows": rows,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    destination = args.report.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if rows and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
