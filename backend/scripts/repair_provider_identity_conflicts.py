"""Safely split canonical opportunities that contain conflicting provider IDs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.sqlite.connection import connect, init_sql
from data.sqlite.opportunities import get_candidate_profile, save_pipeline_result
from opportunities.deduplicate import canonicalize_observations
from opportunities.eligibility import CandidateConstraints
from opportunities.models import SourceRecord
from opportunities.pipeline import evaluate_canonical_opportunities


def _conflict_ids(
    conn: sqlite3.Connection,
    provider: str = "",
    tenant: str = "",
) -> list[str]:
    filters = ""
    params: tuple[str, ...] = ()
    if provider or tenant:
        filters = "AND s.provider=? AND s.provider_tenant=?"
        params = (provider, tenant)
    return [
        str(row[0])
        for row in conn.execute(
            f"""
            SELECT DISTINCT opportunity_id FROM (
                SELECT o.opportunity_id,s.provider,s.provider_tenant
                FROM opportunity_observations o
                JOIN opportunity_source_records s USING(source_record_id)
                WHERE s.provider_requisition_id<>'' {filters}
                GROUP BY o.opportunity_id,s.provider,s.provider_tenant
                HAVING COUNT(DISTINCT s.provider_requisition_id)>1
            )
            ORDER BY opportunity_id
            """,
            params,
        ).fetchall()
    ]


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--provider")
    parser.add_argument("--tenant")
    parser.add_argument("--all-providers", action="store_true")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.all_providers:
        if args.provider or args.tenant:
            parser.error("--all-providers cannot be combined with --provider/--tenant")
        provider = tenant = ""
    else:
        if not args.provider or not args.tenant:
            parser.error("--provider and --tenant are required unless --all-providers is used")
        provider = args.provider.lower()
        tenant = args.tenant.lower()

    db_path = args.db_path.resolve()
    init_sql(str(db_path))
    conn = connect(str(db_path))
    try:
        conflict_ids = _conflict_ids(conn, provider, tenant)
        if not conflict_ids:
            print(json.dumps({"status": "clean", "conflicting_canonicals": 0}, indent=2))
            return 0
        placeholders = _placeholders(conflict_ids)
        records = [
            SourceRecord.model_validate(json.loads(row[0]))
            for row in conn.execute(
                f"""
                SELECT DISTINCT s.payload_json
                FROM opportunity_source_records s
                JOIN opportunity_observations o USING(source_record_id)
                WHERE o.opportunity_id IN ({placeholders})
                ORDER BY s.source_record_id
                """,
                conflict_ids,
            ).fetchall()
        ]
        external_references = {
            table: int(conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE opportunity_id IN ({placeholders})",
                conflict_ids,
            ).fetchone()[0])
            for table in ("candidate_opportunity_events", "leads")
        }
        decision_candidates = {
            str(row[0])
            for row in conn.execute(
                f"""
                SELECT DISTINCT candidate_id FROM candidate_opportunity_decisions
                WHERE opportunity_id IN ({placeholders})
                """,
                conflict_ids,
            ).fetchall()
        }
    finally:
        conn.close()

    canonical = canonicalize_observations(records)
    summary = {
        "status": "dry_run" if not args.apply else "ready",
        "provider": provider or "*",
        "tenant": tenant or "*",
        "conflicting_canonicals": len(conflict_ids),
        "source_observations": len(records),
        "replacement_canonicals": len(canonical),
        "external_references": external_references,
        "decision_candidates": sorted(decision_candidates),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not args.apply:
        return 0
    if any(external_references.values()):
        raise RuntimeError("refusing to split opportunities with candidate events or linked leads")
    if decision_candidates - {args.candidate_id}:
        raise RuntimeError("refusing to discard decisions for unrequested candidates")
    if len(canonical) <= len(conflict_ids):
        raise RuntimeError("replacement did not split the conflicting canonical rows")

    profile = get_candidate_profile(args.candidate_id, db_path=str(db_path))
    if not profile:
        raise RuntimeError(f"candidate profile not found: {args.candidate_id}")
    result = evaluate_canonical_opportunities(
        canonical,
        candidate=CandidateConstraints.model_validate(profile),
    ).model_copy(update={"source_records": records})

    backup_label = "before-provider-split-all" if args.all_providers else "before-provider-split"
    backup_path = db_path.with_name(f"{db_path.stem}.{backup_label}{db_path.suffix}")
    source_conn = sqlite3.connect(str(db_path))
    backup_conn = sqlite3.connect(str(backup_path))
    try:
        source_conn.backup(backup_conn)
    finally:
        backup_conn.close()
        source_conn.close()

    conn = connect(str(db_path))
    try:
        placeholders = _placeholders(conflict_ids)
        conn.execute(
            f"DELETE FROM candidate_opportunity_decisions WHERE opportunity_id IN ({placeholders})",
            conflict_ids,
        )
        conn.execute(
            f"DELETE FROM opportunity_identity_aliases WHERE opportunity_id IN ({placeholders})",
            conflict_ids,
        )
        conn.execute(
            f"DELETE FROM opportunity_observations WHERE opportunity_id IN ({placeholders})",
            conflict_ids,
        )
        conn.execute(
            f"DELETE FROM canonical_opportunities WHERE opportunity_id IN ({placeholders})",
            conflict_ids,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    persisted = save_pipeline_result(
        result,
        candidate_id=args.candidate_id,
        db_path=str(db_path),
    )
    conn = connect(str(db_path))
    try:
        remaining = _conflict_ids(conn, provider, tenant)
    finally:
        conn.close()
    if remaining:
        raise RuntimeError(f"provider identity conflicts remain: {remaining}")
    print(json.dumps({
        "status": "repaired",
        "backup_path": str(backup_path),
        "removed_canonicals": len(conflict_ids),
        "replacement_canonicals": len(canonical),
        "persisted": persisted,
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
