from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.sqlite import connection as sqlite_connection
from data.sqlite.connection import connect, init_sql

# Reuse the connection layer's stable stdlib handle. A legacy graph test
# temporarily shadows sys.modules["sqlite3"] during collection; importing it a
# second time here would otherwise make full-suite order change this module's
# connector while the actual data layer continues to use the real one.
sqlite3 = sqlite_connection.sqlite3

PUBLIC_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "opportunity_source_records": (
        "source_record_id",
        "source_target_id",
        "provider",
        "provider_tenant",
        "provider_requisition_id",
        "canonical_source_url",
        "description_sha256",
        "observed_at",
        "active_hint",
        "payload_json",
        "created_at",
        "updated_at",
    ),
    "canonical_opportunities": (
        "opportunity_id",
        "employer_name",
        "title",
        "location_text",
        "canonical_apply_url",
        "live_status",
        "payload_json",
        "created_at",
        "updated_at",
    ),
    "opportunity_observations": ("opportunity_id", "source_record_id"),
    "opportunity_identity_aliases": ("identity_key", "opportunity_id", "created_at"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp_value(value: Any) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _canonical_freshness(payload_json: str, updated_at: str) -> float:
    try:
        payload = json.loads(payload_json)
        last_seen_at = payload.get("lifecycle", {}).get("last_seen_at")
    except (json.JSONDecodeError, AttributeError):
        last_seen_at = None
    return max(_timestamp_value(last_seen_at), _timestamp_value(updated_at))


def _readonly_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _destination_connection(path: Path) -> sqlite3.Connection:
    # uri=True also makes URI filenames in ATTACH honor mode=ro, while a plain
    # resolved destination path continues to behave as an ordinary database.
    connection = sqlite3.connect(str(path), uri=True, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_columns(connection: sqlite3.Connection, table: str, *, schema: str = "main") -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA {schema}.table_info({table})")}


def _require_public_schema(connection: sqlite3.Connection, *, schema: str = "main") -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type='table'"
        )
    }
    missing_tables = sorted(set(PUBLIC_TABLE_COLUMNS) - tables)
    if missing_tables:
        raise ValueError(f"opportunity index is missing tables: {', '.join(missing_tables)}")
    for table, expected in PUBLIC_TABLE_COLUMNS.items():
        missing_columns = sorted(set(expected) - _table_columns(connection, table, schema=schema))
        if missing_columns:
            raise ValueError(f"{table} is missing columns: {', '.join(missing_columns)}")


def inspect_public_index(source_path: str | Path, *, include_sha256: bool = True) -> dict[str, Any]:
    """Validate and summarize a public opportunity index without modifying it."""
    path = Path(source_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"opportunity index not found: {path}")
    connection = _readonly_connection(path)
    try:
        _require_public_schema(connection)
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        if quick_check != "ok":
            raise ValueError(f"source opportunity index quick_check failed: {quick_check}")
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in PUBLIC_TABLE_COLUMNS
        }
        orphan_observations = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM opportunity_observations observation
                LEFT JOIN canonical_opportunities opportunity
                  ON opportunity.opportunity_id=observation.opportunity_id
                LEFT JOIN opportunity_source_records source
                  ON source.source_record_id=observation.source_record_id
                WHERE opportunity.opportunity_id IS NULL OR source.source_record_id IS NULL
                """
            ).fetchone()[0]
        )
        orphan_aliases = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM opportunity_identity_aliases alias
                LEFT JOIN canonical_opportunities opportunity
                  ON opportunity.opportunity_id=alias.opportunity_id
                WHERE opportunity.opportunity_id IS NULL
                """
            ).fetchone()[0]
        )
        if orphan_observations or orphan_aliases:
            raise ValueError(
                "source opportunity index has orphan relationships: "
                f"observations={orphan_observations}, aliases={orphan_aliases}"
            )
        latest_observed_at = connection.execute(
            "SELECT MAX(observed_at) FROM opportunity_source_records"
        ).fetchone()[0]
        status_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT live_status,COUNT(*) FROM canonical_opportunities GROUP BY live_status"
            )
        }
    finally:
        connection.close()
    return {
        "path": str(path),
        "source_label": path.name,
        "source_size_bytes": path.stat().st_size,
        "source_sha256": _sha256_file(path) if include_sha256 else None,
        "counts": counts,
        "status_counts": status_counts,
        "latest_observed_at": str(latest_observed_at) if latest_observed_at else None,
        "quick_check": quick_check,
        "orphan_observations": orphan_observations,
        "orphan_aliases": orphan_aliases,
    }


def public_index_status(*, db_path: str) -> dict[str, Any]:
    init_sql(db_path)
    connection = connect(db_path)
    try:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in PUBLIC_TABLE_COLUMNS
        }
        status_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                "SELECT live_status,COUNT(*) FROM canonical_opportunities GROUP BY live_status"
            )
        }
        latest_observed_at = connection.execute(
            "SELECT MAX(observed_at) FROM opportunity_source_records"
        ).fetchone()[0]
        last_sync_row = connection.execute(
            """
            SELECT sync_id,source_sha256,source_label,source_size_bytes,
                   source_latest_observed_at,source_counts_json,inserted_counts_json,
                   backup_label,completed_at
            FROM opportunity_index_syncs
            ORDER BY completed_at DESC LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    last_sync = None
    if last_sync_row:
        last_sync = dict(last_sync_row)
        last_sync["source_counts"] = json.loads(last_sync.pop("source_counts_json"))
        last_sync["inserted_counts"] = json.loads(last_sync.pop("inserted_counts_json"))
    return {
        "source_record_count": counts["opportunity_source_records"],
        "canonical_opportunity_count": counts["canonical_opportunities"],
        "observation_count": counts["opportunity_observations"],
        "identity_alias_count": counts["opportunity_identity_aliases"],
        "active_opportunity_count": int(status_counts.get("active", 0)),
        "status_counts": status_counts,
        "latest_observed_at": str(latest_observed_at) if latest_observed_at else None,
        "last_sync": last_sync,
    }


def _collision_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "source_record_identity": int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM source_index.opportunity_source_records source
                JOIN main.opportunity_source_records target USING(source_record_id)
                WHERE source.provider<>target.provider
                   OR source.provider_tenant<>target.provider_tenant
                   OR source.provider_requisition_id<>target.provider_requisition_id
                   OR source.canonical_source_url<>target.canonical_source_url
                   OR source.description_sha256<>target.description_sha256
                """
            ).fetchone()[0]
        ),
        "canonical_identity": int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM source_index.canonical_opportunities source
                JOIN main.canonical_opportunities target USING(opportunity_id)
                WHERE source.employer_name<>target.employer_name
                   OR source.canonical_apply_url<>target.canonical_apply_url
                """
            ).fetchone()[0]
        ),
        "identity_alias": int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM source_index.opportunity_identity_aliases source
                JOIN main.opportunity_identity_aliases target USING(identity_key)
                WHERE source.opportunity_id<>target.opportunity_id
                """
            ).fetchone()[0]
        ),
    }


def _unsafe_canonical_collision_count(connection: sqlite3.Connection) -> int:
    """Count changed same-ID canonicals with no shared authoritative identity."""
    return int(connection.execute(
        """
        SELECT COUNT(*)
        FROM source_index.canonical_opportunities source
        JOIN main.canonical_opportunities target USING(opportunity_id)
        WHERE (source.employer_name<>target.employer_name
            OR source.canonical_apply_url<>target.canonical_apply_url)
          AND NOT EXISTS (
              SELECT 1
              FROM source_index.opportunity_identity_aliases source_alias
              JOIN main.opportunity_identity_aliases target_alias USING(identity_key)
              WHERE source_alias.opportunity_id=source.opportunity_id
                AND target_alias.opportunity_id=target.opportunity_id
                AND (source_alias.identity_key LIKE 'provider:%'
                  OR source_alias.identity_key LIKE 'url:%')
          )
        """
    ).fetchone()[0])


def _alias_reconciliation_plan(
    connection: sqlite3.Connection,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Map historical destination IDs onto current source IDs via exact aliases."""
    rows = connection.execute(
        """
        SELECT source.opportunity_id AS source_id,
               target.opportunity_id AS target_id,
               target_opportunity.opportunity_id IS NOT NULL AS target_exists,
               source_target.opportunity_id IS NOT NULL AS target_still_in_source
        FROM source_index.opportunity_identity_aliases source
        JOIN main.opportunity_identity_aliases target USING(identity_key)
        LEFT JOIN main.canonical_opportunities target_opportunity
          ON target_opportunity.opportunity_id=target.opportunity_id
        LEFT JOIN source_index.canonical_opportunities source_target
          ON source_target.opportunity_id=target.opportunity_id
        WHERE source.opportunity_id<>target.opportunity_id
        GROUP BY source.opportunity_id,target.opportunity_id
        ORDER BY source.opportunity_id,target.opportunity_id
        """
    ).fetchall()
    sources_by_target: dict[str, set[str]] = {}
    unsafe: list[str] = []
    for row in rows:
        source_id = str(row["source_id"])
        target_id = str(row["target_id"])
        if not bool(row["target_exists"]):
            unsafe.append(f"orphan_target:{target_id}")
            continue
        if bool(row["target_still_in_source"]):
            unsafe.append(f"target_still_canonical:{target_id}")
            continue
        sources_by_target.setdefault(target_id, set()).add(source_id)
    for target_id, source_ids in sources_by_target.items():
        if len(source_ids) > 1:
            unsafe.append(f"ambiguous_target:{target_id}:{','.join(sorted(source_ids))}")
    plan = [
        (next(iter(source_ids)), target_id)
        for target_id, source_ids in sorted(sources_by_target.items())
        if len(source_ids) == 1
    ]
    source_ids = {source_id for source_id, _target_id in plan}
    chained = sorted(source_ids & set(sources_by_target))
    unsafe.extend(f"chained_mapping:{opportunity_id}" for opportunity_id in chained)
    return plan, unsafe


def _consolidate_installed_opportunity(
    connection: sqlite3.Connection,
    source_id: str,
    target_id: str,
) -> None:
    """Move local/public references from one historical ID to the current ID."""
    if source_id == target_id:
        return
    connection.execute(
        """
        INSERT OR IGNORE INTO main.opportunity_observations(opportunity_id,source_record_id)
        SELECT ?,source_record_id FROM main.opportunity_observations WHERE opportunity_id=?
        """,
        (source_id, target_id),
    )
    connection.execute(
        "DELETE FROM main.opportunity_observations WHERE opportunity_id=?", (target_id,)
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO main.candidate_opportunity_decisions(
            tenant_id,candidate_id,opportunity_id,rule_version,
            eligibility,decision,payload_json,created_at,updated_at
        )
        SELECT tenant_id,candidate_id,?,rule_version,
               eligibility,decision,payload_json,created_at,updated_at
        FROM main.candidate_opportunity_decisions WHERE opportunity_id=?
        """,
        (source_id, target_id),
    )
    connection.execute(
        "DELETE FROM main.candidate_opportunity_decisions WHERE opportunity_id=?",
        (target_id,),
    )
    connection.execute(
        "UPDATE main.candidate_opportunity_events SET opportunity_id=? WHERE opportunity_id=?",
        (source_id, target_id),
    )
    connection.execute(
        "UPDATE main.leads SET opportunity_id=? WHERE opportunity_id=?",
        (source_id, target_id),
    )
    connection.execute(
        "UPDATE main.opportunity_identity_aliases SET opportunity_id=? WHERE opportunity_id=?",
        (source_id, target_id),
    )
    connection.execute(
        "DELETE FROM main.canonical_opportunities WHERE opportunity_id=?", (target_id,)
    )


def _refresh_newer_canonicals(connection: sqlite3.Connection) -> list[str]:
    """Replace mutable canonical truth only when source evidence is newer."""
    candidates = connection.execute(
        """
        SELECT source.opportunity_id,
               source.employer_name,
               source.title,
               source.location_text,
               source.canonical_apply_url,
               source.live_status,
               source.payload_json,
               source.updated_at,
               target.payload_json AS target_payload_json,
               target.updated_at AS target_updated_at
        FROM source_index.canonical_opportunities source
        JOIN main.canonical_opportunities target USING(opportunity_id)
        """
    ).fetchall()
    updates: list[tuple[str, str, str, str, str, str, str, str]] = []
    for row in candidates:
        source_freshness = _canonical_freshness(row["payload_json"], row["updated_at"])
        target_freshness = _canonical_freshness(
            row["target_payload_json"], row["target_updated_at"]
        )
        if source_freshness <= target_freshness:
            continue
        updates.append(
            (
                row["employer_name"],
                row["title"],
                row["location_text"],
                row["canonical_apply_url"],
                row["live_status"],
                row["payload_json"],
                row["updated_at"],
                row["opportunity_id"],
            )
        )
    connection.executemany(
        """
        UPDATE main.canonical_opportunities
        SET employer_name=?,title=?,location_text=?,canonical_apply_url=?,live_status=?,
            payload_json=?,updated_at=?
        WHERE opportunity_id=?
        """,
        updates,
    )
    return [str(row[-1]) for row in updates]


def _backup_locked_database(destination_path: Path, backup_path: Path) -> None:
    if backup_path.exists():
        raise FileExistsError(f"refusing to overwrite backup: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    source = _readonly_connection(destination_path)
    backup = sqlite3.connect(str(backup_path))
    try:
        source.backup(backup, pages=4096)
        result = str(backup.execute("PRAGMA quick_check").fetchone()[0])
        if result != "ok":
            raise ValueError(f"backup quick_check failed: {result}")
    finally:
        backup.close()
        source.close()


def backup_database(
    database_path: str | Path,
    *,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Create a consistent non-overwriting backup while excluding other writers."""
    database = Path(database_path).expanduser().resolve()
    backup = Path(backup_path).expanduser().resolve()
    if database == backup:
        raise ValueError("database and backup paths must be distinct")
    if not database.is_file():
        raise FileNotFoundError(f"database not found: {database}")
    connection = _destination_connection(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _backup_locked_database(database, backup)
        connection.rollback()
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "database_path": str(database),
        "backup_path": str(backup),
        "backup_size_bytes": backup.stat().st_size,
        "quick_check": "ok",
    }


def sync_public_index(
    source_path: str | Path,
    *,
    destination_path: str | Path,
    backup_path: str | Path,
) -> dict[str, Any]:
    """Atomically merge only canonical public truth into an installed database.

    Candidate profiles, application identities, decisions, outcomes, settings,
    leads, and spend records are intentionally never selected from the source.
    Incompatible stable-key collisions fail closed before the backup or any
    write occurs. Mutable canonical truth is replaced only when the source has
    strictly newer lifecycle evidence; fresher destination truth always wins.
    """
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    backup = Path(backup_path).expanduser().resolve()
    if source == destination or backup in {source, destination}:
        raise ValueError("source, destination, and backup paths must be distinct")
    source_report = inspect_public_index(source, include_sha256=True)
    init_sql(str(destination))
    connection = _destination_connection(destination)
    attached = False
    try:
        _require_public_schema(connection)
        connection.execute("ATTACH DATABASE ? AS source_index", (f"{source.as_uri()}?mode=ro",))
        attached = True
        _require_public_schema(connection, schema="source_index")
        collisions = _collision_counts(connection)
        reconciliation_plan, unsafe_aliases = _alias_reconciliation_plan(connection)
        unsafe_collisions = {
            "source_record_identity": collisions["source_record_identity"],
            "canonical_identity": _unsafe_canonical_collision_count(connection),
            "identity_alias": len(unsafe_aliases),
        }
        if any(unsafe_collisions.values()):
            raise ValueError(
                f"unsafe stable-key collisions: {unsafe_collisions}; "
                f"alias_details={unsafe_aliases[:10]}"
            )

        before = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0])
            for table in PUBLIC_TABLE_COLUMNS
        }
        connection.execute("BEGIN IMMEDIATE")
        _backup_locked_database(destination, backup)
        inserted: dict[str, int] = {}
        insert_order = (
            "opportunity_source_records",
            "canonical_opportunities",
        )
        for table in insert_order:
            columns = PUBLIC_TABLE_COLUMNS[table]
            joined = ",".join(columns)
            previous_changes = connection.total_changes
            connection.execute(
                f"INSERT OR IGNORE INTO main.{table}({joined}) "
                f"SELECT {joined} FROM source_index.{table}"
            )
            inserted[table] = connection.total_changes - previous_changes

        updated_opportunity_ids = _refresh_newer_canonicals(connection)
        updated = {"canonical_opportunities": len(updated_opportunity_ids)}
        for source_id, target_id in reconciliation_plan:
            _consolidate_installed_opportunity(connection, source_id, target_id)
        for table in ("opportunity_observations", "opportunity_identity_aliases"):
            columns = PUBLIC_TABLE_COLUMNS[table]
            joined = ",".join(columns)
            previous_changes = connection.total_changes
            connection.execute(
                f"INSERT OR IGNORE INTO main.{table}({joined}) "
                f"SELECT {joined} FROM source_index.{table}"
            )
            inserted[table] = connection.total_changes - previous_changes

        missing = {
            "source_records": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM source_index.opportunity_source_records source
                    LEFT JOIN main.opportunity_source_records target USING(source_record_id)
                    WHERE target.source_record_id IS NULL
                    """
                ).fetchone()[0]
            ),
            "canonical_opportunities": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM source_index.canonical_opportunities source
                    LEFT JOIN main.canonical_opportunities target USING(opportunity_id)
                    WHERE target.opportunity_id IS NULL
                    """
                ).fetchone()[0]
            ),
            "observations": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM source_index.opportunity_observations source
                    LEFT JOIN main.opportunity_observations target
                      ON target.opportunity_id=source.opportunity_id
                     AND target.source_record_id=source.source_record_id
                    WHERE target.opportunity_id IS NULL
                    """
                ).fetchone()[0]
            ),
            "identity_aliases": int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM source_index.opportunity_identity_aliases source
                    LEFT JOIN main.opportunity_identity_aliases target USING(identity_key)
                    WHERE target.identity_key IS NULL
                    """
                ).fetchone()[0]
            ),
        }
        if any(missing.values()):
            raise ValueError(f"public index verification found missing rows: {missing}")
        foreign_key_violations = len(connection.execute("PRAGMA main.foreign_key_check").fetchall())
        if foreign_key_violations:
            raise ValueError(f"destination foreign_key_check found {foreign_key_violations} violations")
        transaction_quick_check = str(connection.execute("PRAGMA main.quick_check").fetchone()[0])
        if transaction_quick_check != "ok":
            raise ValueError(
                f"destination quick_check failed before commit: {transaction_quick_check}"
            )
        completed_at = _utc_now()
        sync_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO opportunity_index_syncs(
                sync_id,source_sha256,source_label,source_size_bytes,
                source_latest_observed_at,source_counts_json,inserted_counts_json,
                backup_label,completed_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                sync_id,
                source_report["source_sha256"],
                source_report["source_label"],
                source_report["source_size_bytes"],
                source_report["latest_observed_at"],
                json.dumps(source_report["counts"], sort_keys=True, separators=(",", ":")),
                json.dumps(
                    {
                        **inserted,
                        "canonical_opportunities_updated": updated[
                            "canonical_opportunities"
                        ],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                backup.name,
                completed_at,
            ),
        )
        connection.commit()
        after = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0])
            for table in PUBLIC_TABLE_COLUMNS
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        if attached and not connection.in_transaction:
            connection.execute("DETACH DATABASE source_index")
        connection.close()

    checkpoint = _destination_connection(destination)
    try:
        checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        quick_check = str(checkpoint.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        checkpoint.close()
    if quick_check != "ok":
        raise ValueError(f"destination quick_check failed after sync: {quick_check}")
    return {
        "sync_id": sync_id,
        "source": source_report,
        "destination_path": str(destination),
        "backup_path": str(backup),
        "before": before,
        "inserted": inserted,
        "updated": updated,
        "after": after,
        "collisions": collisions,
        "canonical_ids_reconciled": len(reconciliation_plan),
        "missing": missing,
        "foreign_key_violations": foreign_key_violations,
        "quick_check": quick_check,
        "private_tables_imported": [],
        "candidate_decisions_may_require_rescore": bool(updated_opportunity_ids),
        "completed_at": completed_at,
    }
