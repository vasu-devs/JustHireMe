from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.tenancy import LOCAL_TENANT_ID
from core.syndication import (
    is_high_confidence_syndication_payload,
    syndication_identity_key_payload,
)
from data.sqlite.connection import DEFAULT_DB_PATH, get_connection, init_sql
from data.sqlite.opportunity_index import public_index_status as _public_index_status


def _model_json(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    return value.model_dump(mode="json")


def get_public_index_status(*, db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
    return _public_index_status(db_path=db_path)


def _merge_opportunity_payload(existing: dict, incoming: dict, target_id: str) -> dict:
    """Merge materialized truth without importing the business model layer.

    The immutable observation table remains authoritative. The canonical JSON
    keeps a bounded recent view and preserves direct-source display fields when
    a later aggregator observation is less authoritative.
    """
    old_observations = [row for row in existing.get("observations", []) if isinstance(row, dict)]
    new_observations = [row for row in incoming.get("observations", []) if isinstance(row, dict)]
    observations = {
        str(row.get("source_record_id") or ""): row
        for row in [*old_observations, *new_observations]
        if str(row.get("source_record_id") or "")
    }
    recent = sorted(
        observations.values(), key=lambda row: str(row.get("observed_at") or "")
    )[-200:]
    direct_kinds = {"ats", "direct_employer"}
    old_has_direct = any(str(row.get("source_kind") or "") in direct_kinds for row in old_observations)
    new_has_direct = any(str(row.get("source_kind") or "") in direct_kinds for row in new_observations)
    base = existing if old_has_direct and not new_has_direct else incoming
    old_lifecycle = existing.get("lifecycle") if isinstance(existing.get("lifecycle"), dict) else {}
    new_lifecycle = incoming.get("lifecycle") if isinstance(incoming.get("lifecycle"), dict) else {}
    first_seen = min(
        filter(None, [str(old_lifecycle.get("first_seen_at") or ""), str(new_lifecycle.get("first_seen_at") or "")]),
        default="",
    )
    last_seen = max(
        filter(None, [str(old_lifecycle.get("last_seen_at") or ""), str(new_lifecycle.get("last_seen_at") or "")]),
        default="",
    )
    status = str(new_lifecycle.get("status") or "unknown")
    if status == "unknown":
        status = str(old_lifecycle.get("status") or "unknown")
    lifecycle = {
        **old_lifecycle,
        **new_lifecycle,
        "status": status,
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "evidence": list(dict.fromkeys([
            *[str(value) for value in old_lifecycle.get("evidence", []) if value],
            *[str(value) for value in new_lifecycle.get("evidence", []) if value],
        ])),
    }
    return {
        **base,
        "opportunity_id": target_id,
        "identity_keys": sorted({
            *[str(value) for value in existing.get("identity_keys", []) if value],
            *[str(value) for value in incoming.get("identity_keys", []) if value],
        }),
        "lifecycle": lifecycle,
        "observations": recent,
        "dedupe_confidence": max(
            float(existing.get("dedupe_confidence") or 0),
            float(incoming.get("dedupe_confidence") or 0),
        ),
        "dedupe_reasons": sorted({
            *[str(value) for value in existing.get("dedupe_reasons", []) if value],
            *[str(value) for value in incoming.get("dedupe_reasons", []) if value],
        }),
    }


def _payload_provider_identities(payload: dict) -> dict[tuple[str, str], set[str]]:
    identities: dict[tuple[str, str], set[str]] = {}
    for record in payload.get("observations", []):
        if not isinstance(record, dict):
            continue
        requisition_id = str(record.get("provider_requisition_id") or "").strip().lower()
        if not requisition_id:
            continue
        key = (
            str(record.get("provider") or "").strip().lower(),
            str(record.get("provider_tenant") or "").strip().lower(),
        )
        identities.setdefault(key, set()).add(requisition_id)
    return identities


def _payload_provider_identity_conflict(existing: dict, incoming: dict) -> bool:
    left = _payload_provider_identities(existing)
    right = _payload_provider_identities(incoming)
    return any(
        left[key] and right[key] and left[key] != right[key]
        for key in left.keys() & right.keys()
    )


def _historical_syndication_matches(conn, incoming: dict) -> list[tuple[str, str]]:
    """Find proven cross-source copies that arrived in an earlier scan.

    The SQL title predicate keeps the candidate set bounded. The shared
    business predicate then requires matching normalized employer/title,
    authoritative-versus-aggregator provenance, and near-verbatim long-form
    content before any canonical IDs can be consolidated.
    """
    incoming_records: list[dict[str, Any]] = []
    for payload in incoming.get("observations", []):
        if isinstance(payload, dict):
            incoming_records.append(payload)
    matches: dict[str, str] = {}
    for incoming_record in incoming_records:
        title = str(incoming_record.get("title") or "").strip()
        if not title:
            continue
        rows = conn.execute(
            """
            SELECT opportunity_id,payload_json
            FROM canonical_opportunities
            WHERE trim(title)=trim(?) COLLATE NOCASE
            ORDER BY created_at ASC,opportunity_id ASC
            """,
            (title,),
        ).fetchall()
        for row in rows:
            try:
                existing = json.loads(row["payload_json"] or "{}")
            except Exception:
                continue
            if _payload_provider_identity_conflict(existing, incoming):
                continue
            for existing_payload in existing.get("observations", []):
                if not isinstance(existing_payload, dict):
                    continue
                if is_high_confidence_syndication_payload(
                    incoming_record, existing_payload
                ):
                    matches[str(row["opportunity_id"])] = syndication_identity_key_payload(
                        incoming_record, existing_payload
                    )
                    break
    return list(matches.items())


def _consolidate_opportunity_ids(conn, target_id: str, duplicate_ids: list[str]) -> None:
    """Move all local/public references before deleting derived duplicate rows."""
    for duplicate_id in dict.fromkeys(duplicate_ids):
        if not duplicate_id or duplicate_id == target_id:
            continue
        tenant_ids = [
            str(row["tenant_id"])
            for row in conn.execute(
                """
                SELECT tenant_id FROM candidate_opportunity_decisions WHERE opportunity_id=?
                UNION SELECT tenant_id FROM candidate_opportunity_events WHERE opportunity_id=?
                UNION SELECT tenant_id FROM leads WHERE opportunity_id=?
                """,
                (duplicate_id, duplicate_id, duplicate_id),
            ).fetchall()
        ]
        conn.execute(
            """
            INSERT OR IGNORE INTO opportunity_observations(opportunity_id,source_record_id)
            SELECT ?,source_record_id FROM opportunity_observations WHERE opportunity_id=?
            """,
            (target_id, duplicate_id),
        )
        conn.execute("DELETE FROM opportunity_observations WHERE opportunity_id=?", (duplicate_id,))
        for tenant_id in tenant_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_opportunity_decisions(
                    tenant_id,candidate_id,opportunity_id,rule_version,
                    eligibility,decision,payload_json,created_at,updated_at
                )
                SELECT tenant_id,candidate_id,?,rule_version,
                       eligibility,decision,payload_json,created_at,updated_at
                FROM candidate_opportunity_decisions
                WHERE tenant_id=? AND opportunity_id=?
                """,
                (target_id, tenant_id, duplicate_id),
            )
            conn.execute(
                "DELETE FROM candidate_opportunity_decisions WHERE tenant_id=? AND opportunity_id=?",
                (tenant_id, duplicate_id),
            )
            conn.execute(
                """
                UPDATE candidate_opportunity_events SET opportunity_id=?
                WHERE tenant_id=? AND opportunity_id=?
                """,
                (target_id, tenant_id, duplicate_id),
            )
            conn.execute(
                "UPDATE leads SET opportunity_id=? WHERE tenant_id=? AND opportunity_id=?",
                (target_id, tenant_id, duplicate_id),
            )
        conn.execute(
            "UPDATE opportunity_identity_aliases SET opportunity_id=? WHERE opportunity_id=?",
            (target_id, duplicate_id),
        )
        conn.execute("DELETE FROM canonical_opportunities WHERE opportunity_id=?", (duplicate_id,))


def save_candidate_profile(
    candidate_id: str,
    payload: dict,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    if not candidate_id.strip():
        raise ValueError("candidate_id is required")
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO candidate_opportunity_profiles(tenant_id,candidate_id,payload_json)
            VALUES(?,?,?)
            ON CONFLICT(tenant_id,candidate_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                updated_at=datetime('now')
            """,
            (tenant_id, candidate_id, _json(payload)),
        )
        conn.commit()
    finally:
        conn.close()
    return payload


def get_candidate_profile(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM candidate_opportunity_profiles WHERE tenant_id=? AND candidate_id=?",
            (tenant_id, candidate_id),
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row["payload_json"]) if row else {}


def list_candidate_profiles(
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> list[dict]:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT candidate_id,payload_json,updated_at
            FROM candidate_opportunity_profiles
            WHERE tenant_id=? ORDER BY updated_at DESC,candidate_id ASC
            """,
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            **json.loads(row["payload_json"]),
            "candidate_id": row["candidate_id"],
            "profile_updated_at": row["updated_at"],
        }
        for row in rows
    ]


def save_candidate_application_profile(
    candidate_id: str,
    profile: dict,
    *,
    source: str = "local_profile_snapshot",
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    payload_json = _json(profile)
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO candidate_application_profiles(
                tenant_id,candidate_id,payload_json,payload_sha256,source
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(tenant_id,candidate_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                payload_sha256=excluded.payload_sha256,
                source=excluded.source,
                updated_at=datetime('now')
            """,
            (tenant_id, candidate_id, payload_json, digest, source),
        )
        conn.commit()
    finally:
        conn.close()
    return candidate_application_profile_status(candidate_id, db_path=db_path, tenant_id=tenant_id)


def get_candidate_application_profile(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT payload_json FROM candidate_application_profiles
            WHERE tenant_id=? AND candidate_id=?
            """,
            (tenant_id, candidate_id),
        ).fetchone()
    finally:
        conn.close()
    return json.loads(row["payload_json"]) if row else {}


def candidate_application_profile_status(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT payload_json,payload_sha256,source,updated_at
            FROM candidate_application_profiles
            WHERE tenant_id=? AND candidate_id=?
            """,
            (tenant_id, candidate_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"candidate_id": candidate_id, "ready": False}
    profile = json.loads(row["payload_json"] or "{}")
    name = str(profile.get("n") or "").strip()
    summary = str(profile.get("s") or "").strip()
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    email = str(identity.get("email") or "").strip()
    phone = str(identity.get("phone") or "").strip()
    evidence_count = sum(
        len(profile.get(key) or [])
        for key in ("skills", "projects", "exp", "education", "certifications", "achievements")
    )
    return {
        "candidate_id": candidate_id,
        "ready": bool(name and summary and evidence_count and email and phone),
        "has_identity": bool(name),
        "has_contact_identity": bool(email and phone),
        "missing_identity_fields": [
            field for field, value in (("email", email), ("phone", phone)) if not value
        ],
        "has_summary": bool(summary),
        "skill_count": len(profile.get("skills") or []),
        "project_count": len(profile.get("projects") or []),
        "experience_count": len(profile.get("exp") or []),
        "education_count": len(profile.get("education") or []),
        "evidence_count": evidence_count,
        "payload_sha256": row["payload_sha256"],
        "source": row["source"],
        "updated_at": row["updated_at"],
    }


def create_scan_run(
    candidate_id: str,
    *,
    target_count: int,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> str:
    init_sql(db_path)
    run_id = f"opscan_{uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    payload = {"run_id": run_id, "candidate_id": candidate_id, "status": "running", "target_count": target_count}
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO opportunity_scan_runs(run_id,tenant_id,candidate_id,status,payload_json,started_at)
            VALUES(?,?,?,?,?,?)
            """,
            (run_id, tenant_id, candidate_id, "running", _json(payload), now),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def finish_scan_run(
    run_id: str,
    candidate_id: str,
    *,
    status: str,
    payload: dict,
    source_health: list[dict] | None = None,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> None:
    init_sql(db_path)
    completed_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE opportunity_scan_runs
            SET status=?,payload_json=?,completed_at=?,updated_at=datetime('now')
            WHERE run_id=? AND tenant_id=? AND candidate_id=?
            """,
            (status, _json(payload), completed_at, run_id, tenant_id, candidate_id),
        )
        for health in source_health or []:
            conn.execute(
                """
                INSERT INTO opportunity_source_health(tenant_id,candidate_id,target_id,payload_json,attempted_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(tenant_id,candidate_id,target_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    attempted_at=excluded.attempted_at,
                    updated_at=datetime('now')
                """,
                (
                    tenant_id,
                    candidate_id,
                    str(health.get("target_id") or ""),
                    _json(health),
                    str(health.get("attempted_at") or completed_at),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest_scan_run(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT payload_json,started_at,completed_at FROM opportunity_scan_runs
            WHERE tenant_id=? AND candidate_id=? ORDER BY started_at DESC LIMIT 1
            """,
            (tenant_id, candidate_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"candidate_id": candidate_id, "status": "idle"}
    payload = json.loads(row["payload_json"])
    payload["started_at"] = row["started_at"]
    payload["completed_at"] = row["completed_at"]
    return payload


def list_candidate_source_health(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> list[dict]:
    """Return the latest persisted health row per target for one candidate."""
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT payload_json,attempted_at
            FROM opportunity_source_health
            WHERE tenant_id=? AND candidate_id=?
            ORDER BY attempted_at DESC,target_id ASC
            """,
            (tenant_id, candidate_id),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        payload["attempted_at"] = str(payload.get("attempted_at") or row["attempted_at"] or "")
        result.append(payload)
    return result


def save_candidate_source_health(
    candidate_id: str,
    health: dict,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> None:
    """Checkpoint one target immediately so interrupted scans stay auditable."""
    target_id = str(health.get("target_id") or "").strip()
    if not candidate_id.strip() or not target_id:
        raise ValueError("candidate_id and target_id are required")
    attempted_at = str(health.get("attempted_at") or datetime.now(timezone.utc).isoformat())
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO opportunity_source_health(tenant_id,candidate_id,target_id,payload_json,attempted_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(tenant_id,candidate_id,target_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                attempted_at=excluded.attempted_at,
                updated_at=datetime('now')
            """,
            (tenant_id, candidate_id, target_id, _json(health), attempted_at),
        )
        conn.commit()
    finally:
        conn.close()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def save_pipeline_result(
    result,
    *,
    candidate_id: str,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict[str, object]:
    """Atomically upsert public truth and local candidate decisions."""
    if not candidate_id.strip():
        raise ValueError("candidate_id is required")
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        resolved_items: list[tuple[Any, dict, bool, set[str]]] = []
        planned_payloads: dict[str, dict] = {}
        for item in result.opportunities:
            incoming = _model_json(item.opportunity)
            current_providers = {
                str(record.get("provider") or "")
                for record in incoming.get("observations", [])
                if isinstance(record, dict) and record.get("provider")
            }
            aliases: list[str] = []
            identity_keys = [str(value) for value in incoming.get("identity_keys", []) if value]
            if identity_keys:
                placeholders = ",".join("?" for _ in identity_keys)
                alias_matches: dict[str, set[str]] = {}
                for row in conn.execute(
                        f"""
                        SELECT a.opportunity_id,a.identity_key
                        FROM opportunity_identity_aliases a
                        JOIN canonical_opportunities o ON o.opportunity_id=a.opportunity_id
                        WHERE a.identity_key IN ({placeholders})
                        ORDER BY o.created_at ASC,a.opportunity_id ASC
                        """,
                        identity_keys,
                    ).fetchall():
                    alias_matches.setdefault(str(row["opportunity_id"]), set()).add(
                        str(row["identity_key"])
                    )
                for alias_id, matching_keys in alias_matches.items():
                    if any(
                        key.startswith("provider:") or key.startswith("url:")
                        for key in matching_keys
                    ):
                        aliases.append(alias_id)
                        continue
                    alias_row = conn.execute(
                        "SELECT payload_json FROM canonical_opportunities WHERE opportunity_id=?",
                        (alias_id,),
                    ).fetchone()
                    if not alias_row:
                        continue
                    try:
                        existing_alias = json.loads(alias_row["payload_json"] or "{}")
                    except Exception:
                        existing_alias = {}
                    if not _payload_provider_identity_conflict(existing_alias, incoming):
                        aliases.append(alias_id)
            for alias_id, reason in _historical_syndication_matches(conn, incoming):
                aliases.append(alias_id)
                incoming.setdefault("identity_keys", []).append(reason)
                incoming.setdefault("dedupe_reasons", []).append(reason)
                incoming["dedupe_confidence"] = max(
                    float(incoming.get("dedupe_confidence") or 0), 0.99
                )
            aliases = [
                alias_id
                for alias_id in aliases
                if not (
                    alias_id in planned_payloads
                    and _payload_provider_identity_conflict(
                        planned_payloads[alias_id], incoming
                    )
                )
            ]
            aliases = list(dict.fromkeys(aliases))
            target_id = aliases[0] if aliases else str(incoming.get("opportunity_id") or "")
            existing_row = conn.execute(
                "SELECT payload_json FROM canonical_opportunities WHERE opportunity_id=?",
                (target_id,),
            ).fetchone()
            is_new = existing_row is None
            opportunity = {**incoming, "opportunity_id": target_id}
            for alias_id in aliases or ([target_id] if existing_row else []):
                alias_row = conn.execute(
                    "SELECT payload_json FROM canonical_opportunities WHERE opportunity_id=?",
                    (alias_id,),
                ).fetchone()
                if not alias_row:
                    continue
                try:
                    existing = json.loads(alias_row["payload_json"] or "{}")
                    opportunity = _merge_opportunity_payload(existing, opportunity, target_id)
                except Exception:
                    # A corrupt historical payload must not block fresh truth;
                    # rescore_existing reports malformed canonical rows later.
                    continue
            if len(aliases) > 1:
                _consolidate_opportunity_ids(conn, target_id, aliases[1:])
            planned_payloads[target_id] = opportunity
            resolved_items.append((item, opportunity, is_new, current_providers))
        provider_yield: dict[str, dict[str, int]] = {}
        for record in result.source_records:
            values = provider_yield.setdefault(record.provider, {
                "source_records": 0,
                "canonical_opportunities": 0,
                "new_canonical_opportunities": 0,
                "eligible_opportunities": 0,
                "net_new_eligible_opportunities": 0,
            })
            values["source_records"] += 1
        for record in result.source_records:
            payload = _model_json(record)
            conn.execute(
                """
                INSERT INTO opportunity_source_records(
                    source_record_id,source_target_id,provider,provider_tenant,
                    provider_requisition_id,canonical_source_url,description_sha256,
                    observed_at,active_hint,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_record_id) DO UPDATE SET
                    source_target_id=excluded.source_target_id,
                    provider=excluded.provider,
                    provider_tenant=excluded.provider_tenant,
                    provider_requisition_id=excluded.provider_requisition_id,
                    canonical_source_url=excluded.canonical_source_url,
                    description_sha256=excluded.description_sha256,
                    observed_at=excluded.observed_at,
                    active_hint=excluded.active_hint,
                    payload_json=excluded.payload_json,
                    updated_at=datetime('now')
                """,
                (
                    record.source_record_id,
                    record.source_target_id,
                    record.provider,
                    record.provider_tenant,
                    record.provider_requisition_id,
                    record.canonical_source_url,
                    record.description_sha256,
                    record.observed_at.isoformat(),
                    record.active_hint.value,
                    _json(payload),
                ),
            )

        for item, opportunity, is_new, providers in resolved_items:
            applicability = _model_json(item.applicability)
            eligible = str(applicability.get("decision") or "") in {"apply_now", "strong_stretch"}
            for provider in providers:
                values = provider_yield.setdefault(provider, {
                    "source_records": 0,
                    "canonical_opportunities": 0,
                    "new_canonical_opportunities": 0,
                    "eligible_opportunities": 0,
                    "net_new_eligible_opportunities": 0,
                })
                values["canonical_opportunities"] += 1
                values["new_canonical_opportunities"] += int(is_new)
                values["eligible_opportunities"] += int(eligible)
                values["net_new_eligible_opportunities"] += int(is_new and eligible)
            conn.execute(
                """
                INSERT INTO canonical_opportunities(
                    opportunity_id,employer_name,title,location_text,canonical_apply_url,
                    live_status,payload_json
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(opportunity_id) DO UPDATE SET
                    employer_name=excluded.employer_name,
                    title=excluded.title,
                    location_text=excluded.location_text,
                    canonical_apply_url=excluded.canonical_apply_url,
                    live_status=excluded.live_status,
                    payload_json=excluded.payload_json,
                    updated_at=datetime('now')
                """,
                (
                    opportunity["opportunity_id"],
                    opportunity["employer_name"],
                    opportunity["title"],
                    opportunity.get("location_text", ""),
                    opportunity["canonical_apply_url"],
                    (opportunity.get("lifecycle") or {}).get("status", "unknown"),
                    _json(opportunity),
                ),
            )
            for observation in opportunity.get("observations", []):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO opportunity_observations(opportunity_id,source_record_id)
                    VALUES(?,?)
                    """,
                    (opportunity["opportunity_id"], observation["source_record_id"]),
                )
            for identity_key in opportunity.get("identity_keys", []):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO opportunity_identity_aliases(identity_key,opportunity_id)
                    VALUES(?,?)
                    """,
                    (identity_key, opportunity["opportunity_id"]),
                )
            conn.execute(
                """
                INSERT INTO candidate_opportunity_decisions(
                    tenant_id,candidate_id,opportunity_id,rule_version,
                    eligibility,decision,payload_json
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,candidate_id,opportunity_id,rule_version) DO UPDATE SET
                    eligibility=excluded.eligibility,
                    decision=excluded.decision,
                    payload_json=excluded.payload_json,
                    updated_at=datetime('now')
                """,
                (
                    tenant_id,
                    candidate_id,
                    opportunity["opportunity_id"],
                    applicability["rule_version"],
                    applicability["eligibility"],
                    applicability["decision"],
                    _json(applicability),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "source_records": len(result.source_records),
        "opportunities": len(result.opportunities),
        "decisions": len(result.opportunities),
        "provider_yield": provider_yield,
    }


def save_candidate_decisions(
    result,
    *,
    candidate_id: str,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict[str, int]:
    """Persist a rescore without re-resolving or rewriting canonical identity."""
    if not candidate_id.strip():
        raise ValueError("candidate_id is required")
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        saved = 0
        for item in result.opportunities:
            opportunity_id = str(item.opportunity.opportunity_id)
            if not conn.execute(
                "SELECT 1 FROM canonical_opportunities WHERE opportunity_id=?",
                (opportunity_id,),
            ).fetchone():
                raise ValueError(f"canonical opportunity not found: {opportunity_id}")
            applicability = _model_json(item.applicability)
            conn.execute(
                """
                INSERT INTO candidate_opportunity_decisions(
                    tenant_id,candidate_id,opportunity_id,rule_version,
                    eligibility,decision,payload_json
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,candidate_id,opportunity_id,rule_version) DO UPDATE SET
                    eligibility=excluded.eligibility,
                    decision=excluded.decision,
                    payload_json=excluded.payload_json,
                    updated_at=datetime('now')
                """,
                (
                    tenant_id,
                    candidate_id,
                    opportunity_id,
                    applicability["rule_version"],
                    applicability["eligibility"],
                    applicability["decision"],
                    _json(applicability),
                ),
            )
            saved += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"decisions": saved}


def reconcile_missing_direct_opportunities(
    *,
    successful_target_ids: list[str],
    seen_source_record_ids: list[str],
    observed_at: str,
    db_path: str = DEFAULT_DB_PATH,
) -> list[str]:
    """Close roles absent from every authoritative direct target that succeeded.

    Failed/unscanned targets never close anything. Aggregator disappearance is
    not authoritative. Historical observations remain immutable.
    """
    successful = sorted({str(value).strip() for value in successful_target_ids if str(value).strip()})
    if not successful:
        return []
    seen = sorted({str(value).strip() for value in seen_source_record_ids if str(value).strip()})
    init_sql(db_path)
    conn = get_connection(db_path)
    closed_ids: list[str] = []
    try:
        conn.execute("DROP TABLE IF EXISTS temp.current_success_targets")
        conn.execute("DROP TABLE IF EXISTS temp.current_seen_records")
        conn.execute("CREATE TEMP TABLE current_success_targets(target_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TEMP TABLE current_seen_records(source_record_id TEXT PRIMARY KEY)")
        conn.executemany(
            "INSERT INTO current_success_targets(target_id) VALUES(?)",
            [(value,) for value in successful],
        )
        if seen:
            conn.executemany(
                "INSERT INTO current_seen_records(source_record_id) VALUES(?)",
                [(value,) for value in seen],
            )
        impacted = conn.execute(
            """
            SELECT DISTINCT oo.opportunity_id,o.payload_json
            FROM opportunity_observations oo
            JOIN opportunity_source_records r ON r.source_record_id=oo.source_record_id
            JOIN current_success_targets t ON t.target_id=r.source_target_id
            LEFT JOIN current_seen_records s ON s.source_record_id=r.source_record_id
            JOIN canonical_opportunities o ON o.opportunity_id=oo.opportunity_id
            WHERE s.source_record_id IS NULL AND o.live_status NOT IN ('closed','expired')
            """
        ).fetchall()
        for opportunity_row in impacted:
            opportunity_id = str(opportunity_row["opportunity_id"])
            observation_rows = conn.execute(
                """
                SELECT r.source_record_id,r.source_target_id,r.payload_json,
                       CASE WHEN s.source_record_id IS NULL THEN 0 ELSE 1 END AS currently_seen,
                       CASE WHEN t.target_id IS NULL THEN 0 ELSE 1 END AS target_succeeded
                FROM opportunity_observations oo
                JOIN opportunity_source_records r ON r.source_record_id=oo.source_record_id
                LEFT JOIN current_seen_records s ON s.source_record_id=r.source_record_id
                LEFT JOIN current_success_targets t ON t.target_id=r.source_target_id
                WHERE oo.opportunity_id=?
                """,
                (opportunity_id,),
            ).fetchall()
            direct_rows = []
            for row in observation_rows:
                record = json.loads(row["payload_json"] or "{}")
                if str(record.get("source_kind") or "") in {"ats", "direct_employer"}:
                    direct_rows.append(row)
            if not direct_rows:
                continue
            if any(int(row["currently_seen"] or 0) for row in direct_rows):
                continue
            # Any direct source that did not complete successfully keeps the
            # lifecycle unresolved; absence from a failed scan is not closure.
            if any(not int(row["target_succeeded"] or 0) for row in direct_rows):
                continue

            payload = json.loads(opportunity_row["payload_json"] or "{}")
            lifecycle = dict(payload.get("lifecycle") or {})
            lifecycle["status"] = "closed"
            evidence = list(lifecycle.get("evidence") or [])
            marker = f"absent_from_successful_direct_scan:{observed_at}"
            if marker not in evidence:
                evidence.append(marker)
            lifecycle["evidence"] = evidence
            payload["lifecycle"] = lifecycle
            conn.execute(
                """
                UPDATE canonical_opportunities
                SET live_status='closed',payload_json=?,updated_at=datetime('now')
                WHERE opportunity_id=?
                """,
                (_json(payload), opportunity_id),
            )
            closed_ids.append(opportunity_id)
        conn.execute("DROP TABLE IF EXISTS temp.current_success_targets")
        conn.execute("DROP TABLE IF EXISTS temp.current_seen_records")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return closed_ids


def list_candidate_opportunities(
    candidate_id: str,
    *,
    decision: str = "",
    limit: int = 100,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> list[dict]:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        params: list[object] = [tenant_id, candidate_id]
        decision_clause = ""
        if decision:
            decision_clause = " AND d.decision = ?"
            params.append(decision)
        params.append(max(1, min(int(limit or 100), 500)))
        rows = conn.execute(
            f"""
            WITH ranked_decisions AS (
                SELECT d.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.opportunity_id
                           ORDER BY CAST(d.rule_version AS INTEGER) DESC, d.updated_at DESC
                       ) AS decision_rank
                FROM candidate_opportunity_decisions d
                WHERE d.tenant_id=? AND d.candidate_id=?
            )
            SELECT o.payload_json AS opportunity_json,d.payload_json AS decision_json,d.updated_at
            FROM ranked_decisions d
            JOIN canonical_opportunities o ON o.opportunity_id=d.opportunity_id
            WHERE d.decision_rank=1{decision_clause}
            ORDER BY
                CASE d.decision
                    WHEN 'apply_now' THEN 0
                    WHEN 'strong_stretch' THEN 1
                    WHEN 'needs_review' THEN 2
                    ELSE 3
                END,
                d.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "opportunity": json.loads(row["opportunity_json"]),
            "applicability": json.loads(row["decision_json"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def get_candidate_opportunity(
    candidate_id: str,
    opportunity_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            WITH ranked_decisions AS (
                SELECT d.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.opportunity_id
                           ORDER BY CAST(d.rule_version AS INTEGER) DESC, d.updated_at DESC
                       ) AS decision_rank
                FROM candidate_opportunity_decisions d
                WHERE d.tenant_id=? AND d.candidate_id=? AND d.opportunity_id=?
            )
            SELECT o.payload_json AS opportunity_json,d.payload_json AS decision_json,d.updated_at
            FROM ranked_decisions d
            JOIN canonical_opportunities o ON o.opportunity_id=d.opportunity_id
            WHERE d.decision_rank=1
            """,
            (tenant_id, candidate_id, opportunity_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}
    return {
        "opportunity": json.loads(row["opportunity_json"]),
        "applicability": json.loads(row["decision_json"]),
        "updated_at": row["updated_at"],
    }


def list_canonical_opportunities(
    *,
    limit: int = 20_000,
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT payload_json FROM canonical_opportunities ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(int(limit or 20_000), 100_000)),),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row["payload_json"]) for row in rows]


def link_lead_to_opportunity(
    job_id: str,
    opportunity_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> None:
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM canonical_opportunities WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        if not exists:
            raise LookupError(f"opportunity {opportunity_id!r} not found")
        cursor = conn.execute(
            "UPDATE leads SET opportunity_id=? WHERE tenant_id=? AND job_id=?",
            (opportunity_id, tenant_id, job_id),
        )
        if getattr(cursor, "rowcount", 0) == 0:
            raise LookupError(f"lead {job_id!r} not found")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_candidate_event(
    candidate_id: str,
    opportunity_id: str,
    event_type: str,
    *,
    occurred_at: str,
    lead_id: str = "",
    note: str = "",
    metadata: dict | None = None,
    idempotency_key: str = "",
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    """Append one private pilot event; optional idempotency makes UI retries safe."""
    init_sql(db_path)
    if idempotency_key:
        digest = hashlib.sha256(
            f"{tenant_id}|{candidate_id}|{opportunity_id}|{event_type}|{idempotency_key}".encode()
        ).hexdigest()[:32]
        event_id = f"opevt_{digest}"
    else:
        event_id = f"opevt_{uuid4().hex}"
    conn = get_connection(db_path)
    try:
        decision = conn.execute(
            """
            SELECT 1 FROM candidate_opportunity_decisions
            WHERE tenant_id=? AND candidate_id=? AND opportunity_id=? LIMIT 1
            """,
            (tenant_id, candidate_id, opportunity_id),
        ).fetchone()
        if not decision:
            raise LookupError(f"candidate opportunity {opportunity_id!r} not found")
        conn.execute(
            """
            INSERT OR IGNORE INTO candidate_opportunity_events(
                event_id,tenant_id,candidate_id,opportunity_id,lead_id,event_type,
                occurred_at,note,metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id,
                tenant_id,
                candidate_id,
                opportunity_id,
                lead_id,
                event_type,
                occurred_at,
                note,
                _json(metadata or {}),
            ),
        )
        row = conn.execute(
            """
            SELECT event_id,candidate_id,opportunity_id,lead_id,event_type,occurred_at,
                   note,metadata_json,created_at
            FROM candidate_opportunity_events WHERE event_id=? AND tenant_id=?
            """,
            (event_id, tenant_id),
        ).fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    if not row:
        raise RuntimeError("opportunity event was not persisted")
    return {
        "event_id": row["event_id"],
        "candidate_id": row["candidate_id"],
        "opportunity_id": row["opportunity_id"],
        "lead_id": row["lead_id"],
        "event_type": row["event_type"],
        "occurred_at": row["occurred_at"],
        "note": row["note"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "created_at": row["created_at"],
    }


def list_candidate_events(
    candidate_id: str,
    *,
    opportunity_id: str = "",
    limit: int = 500,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> list[dict]:
    init_sql(db_path)
    params: list[object] = [tenant_id, candidate_id]
    opportunity_clause = ""
    if opportunity_id:
        opportunity_clause = " AND opportunity_id=?"
        params.append(opportunity_id)
    params.append(max(1, min(int(limit or 500), 2000)))
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT event_id,candidate_id,opportunity_id,lead_id,event_type,occurred_at,
                   note,metadata_json,created_at
            FROM candidate_opportunity_events
            WHERE tenant_id=? AND candidate_id=?{opportunity_clause}
            ORDER BY occurred_at DESC, created_at DESC LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "event_id": row["event_id"],
            "candidate_id": row["candidate_id"],
            "opportunity_id": row["opportunity_id"],
            "lead_id": row["lead_id"],
            "event_type": row["event_type"],
            "occurred_at": row["occurred_at"],
            "note": row["note"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def candidate_funnel_metrics(
    candidate_id: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    tenant_id: str = LOCAL_TENANT_ID,
) -> dict:
    """Aggregate unique opportunities, never raw event volume, into pilot outcomes."""
    init_sql(db_path)
    conn = get_connection(db_path)
    try:
        event_rows = conn.execute(
            """
            SELECT e.opportunity_id,e.event_type,e.occurred_at,o.payload_json
            FROM candidate_opportunity_events e
            JOIN canonical_opportunities o ON o.opportunity_id=e.opportunity_id
            WHERE e.tenant_id=? AND e.candidate_id=?
            ORDER BY e.occurred_at ASC
            """,
            (tenant_id, candidate_id),
        ).fetchall()
        decision_rows = conn.execute(
            """
            WITH ranked_decisions AS (
                SELECT d.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.opportunity_id
                           ORDER BY CAST(d.rule_version AS INTEGER) DESC, d.updated_at DESC
                       ) AS decision_rank
                FROM candidate_opportunity_decisions d
                WHERE d.tenant_id=? AND d.candidate_id=?
            )
            SELECT decision,COUNT(DISTINCT opportunity_id) AS count
            FROM ranked_decisions WHERE decision_rank=1 GROUP BY decision
            """,
            (tenant_id, candidate_id),
        ).fetchall()
    finally:
        conn.close()

    opportunities_by_event: dict[str, set[str]] = {}
    provider_outcomes: dict[str, dict[str, set[str]]] = {}
    occurred_values: list[str] = []
    for row in event_rows:
        opportunity_id = str(row["opportunity_id"])
        event_type = str(row["event_type"])
        opportunities_by_event.setdefault(event_type, set()).add(opportunity_id)
        occurred_values.append(str(row["occurred_at"] or ""))
        payload = json.loads(row["payload_json"] or "{}")
        observations = payload.get("observations") or []
        primary = max(
            observations,
            key=lambda record: (
                str(record.get("source_kind") or "") in {"ats", "direct_employer"},
                bool(record.get("provider_requisition_id")),
            ),
            default={},
        )
        provider = str(primary.get("provider") or "unknown")
        provider_outcomes.setdefault(provider, {}).setdefault(event_type, set()).add(opportunity_id)

    def union(*event_types: str) -> set[str]:
        result: set[str] = set()
        for event_type in event_types:
            result.update(opportunities_by_event.get(event_type, set()))
        return result

    submitted = union("application_submitted")
    meaningful_contacts = union("recruiter_reply", "screening", "technical_assessment", "interview", "offer")
    interviews = union("interview")
    offers = union("offer")
    funnel = {
        "tracked": len(union("tracked")),
        "application_started": len(union("application_started")),
        "application_submitted": len(submitted),
        "outreach_sent": len(union("outreach_sent")),
        "meaningful_contacts": len(meaningful_contacts),
        "screening_processes": len(union("screening", "technical_assessment", "interview", "offer")),
        "interviews": len(interviews),
        "offers": len(offers),
        "rejections": len(union("rejected")),
        "withdrawn": len(union("withdrawn")),
    }
    denominator = len(submitted)
    rates = {
        "completion_from_tracked_percent": round(100 * denominator / funnel["tracked"], 1) if funnel["tracked"] else 0.0,
        "meaningful_contacts_per_20_applications": round(20 * len(meaningful_contacts) / denominator, 2) if denominator else 0.0,
        "interviews_per_20_applications": round(20 * len(interviews) / denominator, 2) if denominator else 0.0,
        "offers_per_20_applications": round(20 * len(offers) / denominator, 2) if denominator else 0.0,
    }
    source_outcomes = []
    for provider, events in sorted(provider_outcomes.items()):
        provider_submitted = events.get("application_submitted", set())
        provider_contacts = set().union(*(events.get(kind, set()) for kind in (
            "recruiter_reply", "screening", "technical_assessment", "interview", "offer"
        )))
        source_outcomes.append({
            "provider": provider,
            "submitted": len(provider_submitted),
            "meaningful_contacts": len(provider_contacts),
            "interviews": len(events.get("interview", set())),
            "offers": len(events.get("offer", set())),
        })
    return {
        "candidate_id": candidate_id,
        "queue_counts": {str(row["decision"]): int(row["count"] or 0) for row in decision_rows},
        "funnel": funnel,
        "rates": rates,
        "source_outcomes": source_outcomes,
        "first_event_at": min(occurred_values) if occurred_values else None,
        "latest_event_at": max(occurred_values) if occurred_values else None,
    }
