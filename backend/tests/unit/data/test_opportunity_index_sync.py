from __future__ import annotations

import json

import pytest

from data.sqlite import connection as sqlite_connection
from data.sqlite.connection import close_all, connect, init_sql
from data.sqlite.opportunity_index import inspect_public_index, public_index_status, sync_public_index

sqlite3 = sqlite_connection.sqlite3


def _seed_public_index(db_path, *, alias_opportunity_id: str = "opp-1") -> None:
    init_sql(str(db_path))
    connection = connect(str(db_path))
    source_payload = {
        "source_record_id": "source-1",
        "source_target_id": "target-1",
        "provider": "greenhouse",
    }
    opportunity_payload = {
        "opportunity_id": "opp-1",
        "employer_name": "Example AI",
        "title": "Software Engineering Intern",
        "identity_keys": ["provider:greenhouse:example:req-1"],
    }
    connection.execute(
        """
        INSERT INTO opportunity_source_records(
            source_record_id,source_target_id,provider,provider_tenant,
            provider_requisition_id,canonical_source_url,description_sha256,
            observed_at,active_hint,payload_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "source-1",
            "target-1",
            "greenhouse",
            "example",
            "req-1",
            "https://example.test/jobs/req-1",
            "abc123",
            "2026-08-25T00:00:00Z",
            "active",
            json.dumps(source_payload),
        ),
    )
    connection.execute(
        """
        INSERT INTO canonical_opportunities(
            opportunity_id,employer_name,title,location_text,canonical_apply_url,
            live_status,payload_json
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (
            "opp-1",
            "Example AI",
            "Software Engineering Intern",
            "Remote - India",
            "https://example.test/jobs/req-1",
            "active",
            json.dumps(opportunity_payload),
        ),
    )
    connection.execute(
        "INSERT INTO opportunity_observations(opportunity_id,source_record_id) VALUES(?,?)",
        ("opp-1", "source-1"),
    )
    connection.execute(
        "INSERT INTO opportunity_identity_aliases(identity_key,opportunity_id) VALUES(?,?)",
        ("provider:greenhouse:example:req-1", alias_opportunity_id),
    )
    connection.execute(
        """
        INSERT INTO candidate_opportunity_profiles(tenant_id,candidate_id,payload_json)
        VALUES('tenant-source','synthetic-source-candidate','{}')
        """
    )
    connection.execute(
        """
        INSERT INTO candidate_opportunity_decisions(
            tenant_id,candidate_id,opportunity_id,rule_version,eligibility,decision,payload_json
        ) VALUES('tenant-source','synthetic-source-candidate','opp-1','test','eligible','apply_now','{}')
        """
    )
    connection.execute(
        """
        INSERT INTO leads(job_id,title,company,url,platform,status)
        VALUES('source-lead','Synthetic','Source only','https://example.test/source','test','discovered')
        """
    )
    connection.commit()
    connection.close()


def _seed_destination(db_path) -> None:
    init_sql(str(db_path))
    connection = connect(str(db_path))
    connection.execute(
        """
        INSERT INTO leads(job_id,title,company,url,platform,status)
        VALUES('existing-lead','Existing','Preserved','https://example.test/existing','test','approved')
        """
    )
    connection.commit()
    connection.close()


def test_public_index_sync_is_atomic_idempotent_and_excludes_private_state(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    first_backup = tmp_path / "before-first.sqlite3"
    second_backup = tmp_path / "before-second.sqlite3"
    _seed_public_index(source)
    _seed_destination(destination)
    close_all()

    source_report = inspect_public_index(source)
    assert source_report["counts"]["canonical_opportunities"] == 1
    first = sync_public_index(source, destination_path=destination, backup_path=first_backup)
    assert first["inserted"] == {
        "opportunity_source_records": 1,
        "canonical_opportunities": 1,
        "opportunity_observations": 1,
        "opportunity_identity_aliases": 1,
    }
    assert first["private_tables_imported"] == []
    assert first["quick_check"] == "ok"

    destination_connection = sqlite3.connect(destination)
    assert destination_connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
    assert destination_connection.execute(
        "SELECT job_id FROM leads"
    ).fetchone()[0] == "existing-lead"
    assert destination_connection.execute(
        "SELECT COUNT(*) FROM candidate_opportunity_profiles"
    ).fetchone()[0] == 0
    assert destination_connection.execute(
        "SELECT COUNT(*) FROM candidate_opportunity_decisions"
    ).fetchone()[0] == 0
    destination_connection.close()

    backup_connection = sqlite3.connect(first_backup)
    assert backup_connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
    assert backup_connection.execute(
        "SELECT COUNT(*) FROM canonical_opportunities"
    ).fetchone()[0] == 0
    backup_connection.close()

    second = sync_public_index(source, destination_path=destination, backup_path=second_backup)
    assert all(value == 0 for value in second["inserted"].values())
    assert second["updated"] == {"canonical_opportunities": 0}
    assert inspect_public_index(source)["source_sha256"] == source_report["source_sha256"]
    status = public_index_status(db_path=str(destination))
    assert status["source_record_count"] == 1
    assert status["canonical_opportunity_count"] == 1
    assert status["active_opportunity_count"] == 1
    assert status["last_sync"]["source_sha256"] == source_report["source_sha256"]


def test_public_index_sync_updates_only_strictly_newer_canonical_truth(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    backup = tmp_path / "before-refresh.sqlite3"
    newer_destination_backup = tmp_path / "before-newer-destination.sqlite3"
    _seed_public_index(source)
    _seed_public_index(destination)
    close_all()

    source_connection = sqlite3.connect(source)
    source_payload = {
        "opportunity_id": "opp-1",
        "employer_name": "Example AI",
        "title": "Software Engineering Intern",
        "identity_keys": ["provider:greenhouse:example:req-1"],
        "lifecycle": {"last_seen_at": "2026-08-25T12:00:00Z", "live_status": "active"},
    }
    source_connection.execute(
        """
        UPDATE canonical_opportunities
        SET title='Senior Software Engineering Intern',live_status='active',payload_json=?,
            updated_at='2026-08-25T12:00:00Z'
        WHERE opportunity_id='opp-1'
        """,
        (json.dumps(source_payload),),
    )
    source_connection.commit()
    source_connection.close()

    destination_connection = sqlite3.connect(destination)
    destination_payload = {
        **source_payload,
        "lifecycle": {"last_seen_at": "2026-08-24T12:00:00Z", "live_status": "unknown"},
    }
    destination_connection.execute(
        """
        UPDATE canonical_opportunities
        SET live_status='unknown',payload_json=?,updated_at='2026-08-24T12:00:00Z'
        WHERE opportunity_id='opp-1'
        """,
        (json.dumps(destination_payload),),
    )
    destination_connection.commit()
    destination_connection.close()

    result = sync_public_index(source, destination_path=destination, backup_path=backup)

    assert result["inserted"] == {
        "opportunity_source_records": 0,
        "canonical_opportunities": 0,
        "opportunity_observations": 0,
        "opportunity_identity_aliases": 0,
    }
    assert result["updated"] == {"canonical_opportunities": 1}
    assert result["candidate_decisions_may_require_rescore"] is True
    installed = sqlite3.connect(destination)
    assert installed.execute(
        "SELECT live_status FROM canonical_opportunities WHERE opportunity_id='opp-1'"
    ).fetchone()[0] == "active"
    assert installed.execute(
        "SELECT title FROM canonical_opportunities WHERE opportunity_id='opp-1'"
    ).fetchone()[0] == "Senior Software Engineering Intern"
    newer_destination_payload = {
        **source_payload,
        "lifecycle": {"last_seen_at": "2026-08-26T12:00:00Z", "live_status": "closed"},
    }
    installed.execute(
        """
        UPDATE canonical_opportunities
        SET live_status='closed',payload_json=?,updated_at='2026-08-26T12:00:00Z'
        WHERE opportunity_id='opp-1'
        """,
        (json.dumps(newer_destination_payload),),
    )
    installed.commit()
    installed.close()

    older_result = sync_public_index(
        source,
        destination_path=destination,
        backup_path=newer_destination_backup,
    )
    assert older_result["updated"] == {"canonical_opportunities": 0}
    assert older_result["candidate_decisions_may_require_rescore"] is False
    preserved = sqlite3.connect(destination)
    assert preserved.execute(
        "SELECT live_status FROM canonical_opportunities WHERE opportunity_id='opp-1'"
    ).fetchone()[0] == "closed"
    assert preserved.execute(
        "SELECT title FROM canonical_opportunities WHERE opportunity_id='opp-1'"
    ).fetchone()[0] == "Senior Software Engineering Intern"
    preserved.close()


def test_public_index_sync_reconciles_historical_alias_owner_and_local_refs(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    backup = tmp_path / "before-reconcile.sqlite3"
    _seed_public_index(source)
    _seed_public_index(destination)
    close_all()

    connection = sqlite3.connect(destination)
    connection.execute(
        "UPDATE canonical_opportunities SET opportunity_id='opp-historical' WHERE opportunity_id='opp-1'"
    )
    connection.execute(
        "UPDATE opportunity_observations SET opportunity_id='opp-historical' WHERE opportunity_id='opp-1'"
    )
    connection.execute(
        "UPDATE opportunity_identity_aliases SET opportunity_id='opp-historical' WHERE opportunity_id='opp-1'"
    )
    connection.execute(
        "UPDATE candidate_opportunity_decisions SET opportunity_id='opp-historical' WHERE opportunity_id='opp-1'"
    )
    connection.execute(
        "UPDATE leads SET opportunity_id='opp-historical' WHERE job_id='source-lead'"
    )
    connection.commit()
    connection.close()

    result = sync_public_index(source, destination_path=destination, backup_path=backup)

    assert result["canonical_ids_reconciled"] == 1
    assert result["collisions"]["identity_alias"] == 1
    installed = sqlite3.connect(destination)
    assert installed.execute(
        "SELECT opportunity_id FROM opportunity_identity_aliases"
    ).fetchone()[0] == "opp-1"
    assert installed.execute(
        "SELECT opportunity_id FROM candidate_opportunity_decisions"
    ).fetchone()[0] == "opp-1"
    assert installed.execute(
        "SELECT opportunity_id FROM leads WHERE job_id='source-lead'"
    ).fetchone()[0] == "opp-1"
    assert installed.execute(
        "SELECT COUNT(*) FROM canonical_opportunities"
    ).fetchone()[0] == 1
    installed.close()


def test_public_index_sync_fails_closed_on_alias_collision_before_backup(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    backup = tmp_path / "must-not-exist.sqlite3"
    _seed_public_index(source)
    _seed_public_index(destination, alias_opportunity_id="different-opportunity")
    close_all()

    with pytest.raises(ValueError, match="unsafe stable-key collisions"):
        sync_public_index(source, destination_path=destination, backup_path=backup)
    assert not backup.exists()


def test_public_index_inspection_rejects_orphan_relationships(tmp_path) -> None:
    source = tmp_path / "source.sqlite3"
    _seed_public_index(source)
    close_all()
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        "INSERT INTO opportunity_observations(opportunity_id,source_record_id) VALUES('missing','source-1')"
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="orphan relationships"):
        inspect_public_index(source, include_sha256=False)
