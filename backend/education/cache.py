"""Mon Master local cache — persistent SQLite cache for Master program data.

The Mon Master API is rate-limited and can be slow. This module provides a
local SQLite-backed cache that syncs the full catalog periodically and
answers queries from local storage.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from data.sqlite.connection import DEFAULT_DB_PATH, connect
from education.mon_master_client import _MON_MASTER_BASE

_LOG = logging.getLogger(__name__)

_CACHE_STALE_DAYS = 7


def _ensure_table(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create mon_master_programs table if it doesn't exist."""
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mon_master_programs (
                program_id TEXT PRIMARY KEY,
                title TEXT,
                university TEXT,
                city TEXT,
                uai_code TEXT,
                domain TEXT,
                modalities TEXT,
                capacity INTEGER DEFAULT 0,
                program_url TEXT,
                updated_at TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_mm_city ON mon_master_programs(city);
            CREATE INDEX IF NOT EXISTS idx_mm_domain ON mon_master_programs(domain);
            CREATE INDEX IF NOT EXISTS idx_mm_modalities ON mon_master_programs(modalities);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_program(row) -> dict:
    """Convert a DB row to a program dict matching API format."""
    return {
        "for_intitule": row[1] or "",
        "etab_nom": row[2] or "",
        "etab_ville": row[3] or "",
        "etab_uai": row[4] or "",
        "for_dom": row[5] or "",
        "for_modalite": row[6] or "",
        "for_capacite": row[7] or 0,
        "for_lien_fiche_principal": row[8] or "",
    }


def _build_program_id(program: dict) -> str:
    uai = program.get("etab_uai") or ""
    intitule = program.get("for_intitule") or ""
    return f"{uai}-{intitule}".replace(" ", "_").replace("/", "_")[:120]


def _serialize_field(value) -> str:
    """Serialize a field that may be a list or None into a string for SQLite."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v is not None)
    return str(value)


class MonMasterCache:
    """SQLite-backed cache for Mon Master program data."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        _ensure_table(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def sync(self) -> int:
        """Download full Mon Master catalog and store locally. Returns count.

        Fetches all records via paginated requests (~100 per page) and
        upserts them into the local SQLite table.
        """
        _LOG.info("MonMasterCache sync starting...")

        all_results: list[dict] = []
        page_size = 100
        offset = 0
        max_offset = 10000  # API hard limit
        max_pages = 200  # Safety cap

        try:
            import httpx
            client_cls = httpx.Client
            timeout = httpx.Timeout(60.0)
        except Exception:
            import requests as _requests
            client_cls = _requests.Session
            timeout = 60

        with client_cls() as client:
            for page in range(max_pages):
                if offset >= max_offset:
                    _LOG.info("MonMasterCache sync reached API offset limit at %s records", len(all_results))
                    break
                try:
                    if client_cls.__name__ == "Client":  # httpx
                        resp = client.get(
                            _MON_MASTER_BASE,
                            params={"limit": page_size, "offset": offset},
                            timeout=timeout,
                        )
                    else:  # requests
                        resp = client.get(
                            _MON_MASTER_BASE,
                            params={"limit": page_size, "offset": offset},
                            timeout=timeout,
                        )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    _LOG.warning("Mon Master API sync error at offset %s: %s", offset, exc)
                    break

                results = data.get("results") or []
                if not results:
                    break

                all_results.extend(results)
                _LOG.debug("MonMasterCache sync page %s: +%s records (total %s)", page + 1, len(results), len(all_results))

                if len(results) < page_size:
                    break
                offset += page_size

        if not all_results:
            _LOG.warning("Mon Master sync returned 0 results")
            return 0

        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            for prog in all_results:
                pid = _build_program_id(prog)
                conn.execute(
                    """
                    INSERT INTO mon_master_programs(
                        program_id, title, university, city, uai_code,
                        domain, modalities, capacity, program_url, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(program_id) DO UPDATE SET
                        title=excluded.title,
                        university=excluded.university,
                        city=excluded.city,
                        uai_code=excluded.uai_code,
                        domain=excluded.domain,
                        modalities=excluded.modalities,
                        capacity=excluded.capacity,
                        program_url=excluded.program_url,
                        updated_at=excluded.updated_at
                    """,
                    (
                        pid,
                        prog.get("for_intitule") or "",
                        prog.get("etab_nom") or "",
                        prog.get("etab_ville") or "",
                        prog.get("etab_uai") or "",
                        prog.get("for_dom") or "",
                        _serialize_field(prog.get("for_modalite")),
                        int(prog.get("for_capacite") or 0),
                        prog.get("for_lien_fiche_principal") or "",
                        now,
                    ),
                )
            conn.commit()
        except Exception as exc:
            _LOG.error("MonMasterCache sync DB error: %s", exc)
            conn.rollback()
            return 0
        finally:
            conn.close()

        _LOG.info("MonMasterCache sync complete: %s programs", len(all_results))
        return len(all_results)

    def query(
        self,
        city: str,
        domain: str | None = None,
        require_alternance: bool = True,
    ) -> list[dict]:
        """Query local cache for programs matching criteria.

        Args:
            city: City name (uppercase or lowercase, will be LIKE-matched).
            domain: Optional academic domain filter.
            require_alternance: If True, only return programs whose modalities
                contain 'Alternance'.

        Returns:
            List of program dicts in API-compatible format.
        """
        conn = self._connect()
        try:
            clauses: list[str] = ["city LIKE ?"]
            params: list[Any] = [f"%{city.upper()}%"]

            if domain:
                clauses.append("domain LIKE ?")
                params.append(f"%{domain.upper()}%")

            if require_alternance:
                clauses.append("modalities LIKE ?")
                params.append("%Alternance%")

            sql = (
                "SELECT program_id, title, university, city, uai_code, "
                "domain, modalities, capacity, program_url "
                "FROM mon_master_programs WHERE " + " AND ".join(clauses)
            )
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [_row_to_program(row) for row in rows]

    def is_stale(self) -> bool:
        """Return True if cache is empty or older than CACHE_STALE_DAYS."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(updated_at) FROM mon_master_programs"
            ).fetchone()
        finally:
            conn.close()

        count = row[0] if row else 0
        if count == 0:
            return True

        updated_at = row[1] if row else ""
        if not updated_at:
            return True

        try:
            last = datetime.fromisoformat(updated_at)
            delta = datetime.now(timezone.utc) - last
            return delta.days > _CACHE_STALE_DAYS
        except Exception:
            return True

    def count(self) -> int:
        """Return number of cached programs."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT COUNT(*) FROM mon_master_programs").fetchone()
        finally:
            conn.close()
        return row[0] if row else 0
