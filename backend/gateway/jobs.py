from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from data.sqlite.connection import DEFAULT_DB_PATH, connect, run_migrations


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str
    progress: int = 0
    input_json: dict[str, Any] = field(default_factory=dict)
    result_json: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


class JobStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._initialized = False

    def init(self) -> None:
        if self._initialized:
            return
        run_migrations(self.db_path)
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_jobs(
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    input_json TEXT DEFAULT '{}',
                    result_json TEXT DEFAULT '{}',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT '',
                    started_at TEXT DEFAULT '',
                    finished_at TEXT DEFAULT ''
                )
                """
            )
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def create(self, kind: str, payload: dict[str, Any] | None = None) -> JobRecord:
        self.init()
        record = JobRecord(job_id=f"{kind}-{uuid.uuid4().hex[:12]}", kind=kind, status="queued", input_json=payload or {}, created_at=_now())
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO gateway_jobs(job_id, kind, status, progress, input_json, result_json, error, created_at, started_at, finished_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.job_id,
                    record.kind,
                    record.status,
                    record.progress,
                    json.dumps(record.input_json),
                    "{}",
                    "",
                    record.created_at,
                    "",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return record

    def update(self, job_id: str, *, status: str | None = None, progress: int | None = None, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.init()
        record = self.get(job_id)
        if not record:
            return
        status = status or record.status
        started_at = record.started_at or (_now() if status == "running" else "")
        finished_at = record.finished_at or (_now() if status in {"succeeded", "failed", "cancelled"} else "")
        conn = connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE gateway_jobs
                SET status=?, progress=?, result_json=?, error=?, started_at=?, finished_at=?
                WHERE job_id=?
                """,
                (
                    status,
                    record.progress if progress is None else progress,
                    json.dumps(record.result_json if result is None else result),
                    record.error if error is None else error,
                    started_at,
                    finished_at,
                    job_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def request_cancel(self, job_id: str) -> None:
        self.update(job_id, status="cancel_requested")

    def is_cancel_requested(self, job_id: str) -> bool:
        record = self.get(job_id)
        return bool(record and record.status == "cancel_requested")

    def get(self, job_id: str) -> JobRecord | None:
        self.init()
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT job_id, kind, status, progress, input_json, result_json, error, created_at, started_at, finished_at
                FROM gateway_jobs WHERE job_id=?
                """,
                (job_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return JobRecord(
            job_id=row[0],
            kind=row[1],
            status=row[2],
            progress=int(row[3] or 0),
            input_json=json.loads(row[4] or "{}"),
            result_json=json.loads(row[5] or "{}"),
            error=row[6] or "",
            created_at=row[7] or "",
            started_at=row[8] or "",
            finished_at=row[9] or "",
        )


_job_store = JobStore()


def get_job_store() -> JobStore:
    return _job_store
