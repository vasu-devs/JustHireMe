from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opportunities.eligibility import OPPORTUNITY_RULE_VERSION
from opportunities.models import CanonicalOpportunity, SourceRecord


_PRIVATE_KEY_MARKERS = (
    "candidate",
    "email",
    "phone",
    "resume",
    "cv",
    "token",
    "secret",
    "password",
    "cookie",
    "demographic",
    "application_form",
    "application_questions",
)

_LOCAL_STATE_TABLES = (
    "leads",
    "candidate_opportunity_profiles",
    "candidate_application_profiles",
    "candidate_opportunity_decisions",
    "candidate_opportunity_events",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strictly validate opportunity payloads and audit public metadata."
    )
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--provider", default="")
    parser.add_argument("--report")
    return parser


def _private_keys(value: Any, *, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if any(marker in key.lower() for marker in _PRIVATE_KEY_MARKERS):
                found.append(path)
            found.extend(_private_keys(child, prefix=path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_private_keys(child, prefix=f"{prefix}[{index}]"))
    return found


def _present(metadata: list[dict[str, Any]], key: str) -> int:
    return sum(item.get(key) not in (None, "", [], {}) for item in metadata)


def main() -> int:
    args = _parser().parse_args()
    path = args.db_path.expanduser().resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        source_rows = connection.execute(
            "SELECT provider,source_record_id,payload_json FROM opportunity_source_records"
        ).fetchall()
        canonical_rows = connection.execute(
            "SELECT opportunity_id,payload_json FROM canonical_opportunities"
        ).fetchall()
        invalid_sources: list[dict[str, str]] = []
        invalid_canonicals: list[dict[str, str]] = []
        all_source_payloads: list[dict[str, Any]] = []
        for row in source_rows:
            try:
                payload = json.loads(row["payload_json"])
                SourceRecord.model_validate(payload)
                all_source_payloads.append(payload)
            except Exception as exc:  # pragma: no cover - evidence surfaced in report
                invalid_sources.append(
                    {"provider": row["provider"], "id": row["source_record_id"], "error": str(exc)}
                )
        for row in canonical_rows:
            try:
                CanonicalOpportunity.model_validate_json(row["payload_json"])
            except Exception as exc:  # pragma: no cover - evidence surfaced in report
                invalid_canonicals.append(
                    {"id": row["opportunity_id"], "error": str(exc)}
                )

        provider_payloads: list[dict[str, Any]] = []
        provider_metadata: list[dict[str, Any]] = []
        if args.provider:
            rows = connection.execute(
                """
                WITH latest AS (
                    SELECT payload_json,
                           ROW_NUMBER() OVER (
                               PARTITION BY provider,provider_tenant,
                                            provider_requisition_id,canonical_source_url
                               ORDER BY observed_at DESC,source_record_id DESC
                           ) AS position
                    FROM opportunity_source_records
                    WHERE provider=?
                )
                SELECT payload_json FROM latest WHERE position=1
                """,
                (args.provider,),
            ).fetchall()
            provider_payloads = [json.loads(row["payload_json"]) for row in rows]
            provider_metadata = [payload.get("public_metadata") or {} for payload in provider_payloads]

        metadata_field_completeness = Counter(
            key
            for metadata in provider_metadata
            for key, value in metadata.items()
            if value not in (None, "", [], {})
        )
        source_fields = (
            "apply_url",
            "attribution",
            "canonical_source_url",
            "description_full",
            "description_sha256",
            "deadline_at",
            "location_text",
            "provider_deadline_text",
            "provider_published_text",
            "provider_requisition_id",
            "provider_updated_text",
            "published_at",
            "raw_payload_sha256",
            "source_target_id",
            "updated_at",
            "workplace_text",
        )
        source_field_completeness = {
            field: sum(payload.get(field) not in (None, "", [], {}) for payload in provider_payloads)
            for field in source_fields
        }
        all_source_field_completeness = {}
        for field in source_fields:
            count = sum(
                payload.get(field) not in (None, "", [], {})
                for payload in all_source_payloads
            )
            all_source_field_completeness[field] = {
                "count": count,
                "percent": round(100 * count / len(all_source_payloads), 2)
                if all_source_payloads else 0.0,
            }
        employer_domain_count = sum(
            payload.get("employer_domain") not in (None, "", [], {})
            for payload in all_source_payloads
        )
        all_source_field_completeness["employer_domain"] = {
            "count": employer_domain_count,
            "percent": round(100 * employer_domain_count / len(all_source_payloads), 2)
            if all_source_payloads else 0.0,
        }

        private_keys = sorted(
            {
                key
                for metadata in provider_metadata
                for key in _private_keys(metadata)
            }
        )
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        result = {
            "path": str(path),
            "quick_check": quick_check,
            "source_records": len(source_rows),
            "all_source_field_completeness": all_source_field_completeness,
            "canonical_opportunities": len(canonical_rows),
            "invalid_source_records": len(invalid_sources),
            "invalid_canonical_opportunities": len(invalid_canonicals),
            "invalid_source_samples": invalid_sources[:10],
            "invalid_canonical_samples": invalid_canonicals[:10],
            "representative_decisions": {
                str(row["decision"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT decision,COUNT(*) AS count
                    FROM candidate_opportunity_decisions
                    WHERE candidate_id='phase0-representative-cse'
                      AND rule_version=?
                    GROUP BY decision
                    """,
                    (OPPORTUNITY_RULE_VERSION,),
                ).fetchall()
            },
            "representative_rule_version": OPPORTUNITY_RULE_VERSION,
            "provider": args.provider or None,
            "provider_latest_records": len(provider_metadata),
            "provider_public_metadata_present": sum(bool(item) for item in provider_metadata),
            "provider_active_hints": dict(sorted(Counter(
                str(payload.get("active_hint") or "unknown") for payload in provider_payloads
            ).items())),
            "provider_tenant_counts": dict(sorted(Counter(
                str(payload.get("provider_tenant") or "")
                for payload in provider_payloads
                if payload.get("provider_tenant")
            ).items())),
            "provider_unique_requisition_ids": len({
                str(payload.get("provider_requisition_id"))
                for payload in provider_payloads
                if payload.get("provider_requisition_id")
            }),
            "provider_unique_canonical_urls": len({
                str(payload.get("canonical_source_url"))
                for payload in provider_payloads
                if payload.get("canonical_source_url")
            }),
            "provider_metadata_field_completeness": dict(sorted(metadata_field_completeness.items())),
            "provider_source_field_completeness": source_field_completeness,
            "provider_portal_generation_counts": dict(sorted(Counter(
                str(metadata.get("portal_generation") or "embedded")
                for metadata in provider_metadata
            ).items())),
            "provider_metadata_fields": {
                "employment_type": _present(provider_metadata, "employment_type"),
                "applicant_location_requirements": _present(
                    provider_metadata, "applicant_location_requirements"
                ),
                "base_salary": _present(provider_metadata, "base_salary"),
                "employer_domain": _present(provider_metadata, "employer_domain"),
                "company_logo": _present(provider_metadata, "company_logo"),
            },
            "provider_forbidden_public_metadata_keys": private_keys,
            "local_state_counts": {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in _LOCAL_STATE_TABLES
                if table in tables
            },
        }
    finally:
        connection.close()

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if quick_check != "ok" or invalid_sources or invalid_canonicals or private_keys else 0


if __name__ == "__main__":
    raise SystemExit(main())
