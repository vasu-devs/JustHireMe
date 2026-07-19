"""One-shot repair of stored lead rows.

Lives in ``discovery`` (not ``data``) because the repair re-runs discovery's
own parsers over stored rows — ``data`` must never import ``discovery``.
"""

from __future__ import annotations

import re

from core.logging import get_logger

_log = get_logger(__name__)


def normalize_stored_leads(db_path: str | None = None) -> dict:
    """Idempotent one-shot repair of STORED lead rows (defaults to the app DB).

    - ``hn_hiring`` rows whose title is a raw comment dump from the pre-parser
      era (>120 chars or 2+ pipe separators) get company/title re-derived via
      ``hn_company_role``.
    - ``remoteok`` rows get the injected anti-spam paragraph stripped and
      mojibake repaired in title + description.

    Runs in one transaction and returns
    ``{"titles_fixed": N, "descriptions_cleaned": N}``; a second run is a
    no-op returning zeros.
    """
    from data.sqlite.connection import get_connection
    from discovery.normalizer import _junk_title, hn_company_role
    from discovery.sources.rss import repair_mojibake, strip_remoteok_noise

    def _needs_hn_repair(title: str, company: str) -> bool:
        if len(title) > 120 or title.count("|") >= 2:
            return True  # pre-parser comment dump
        if _junk_title(title):
            return True  # email / fragment stored as title
        # Every "Hiring at <company>" fallback is worth a re-derivation pass:
        # parser vocabulary keeps growing (C-suite roles landed late), and when
        # the description still yields nothing better the re-derive returns the
        # same title and writes nothing — idempotent by construction. Also
        # covers the inverted case (role stored as company).
        return title == f"Hiring at {company}"

    conn = get_connection(db_path)
    counts = {"titles_fixed": 0, "descriptions_cleaned": 0}
    try:
        rows = conn.execute(
            "SELECT job_id, title, company, description, platform FROM leads "
            "WHERE platform IN ('hn_hiring', 'remoteok')"
        ).fetchall()
        for row in rows:
            job_id = row["job_id"]
            title = str(row["title"] or "")
            description = str(row["description"] or "")
            if str(row["platform"] or "") == "hn_hiring":
                if not _needs_hn_repair(title, str(row["company"] or "")):
                    continue
                company, new_title = hn_company_role(description or title)
                if new_title and new_title != title:
                    conn.execute(
                        "UPDATE leads SET title = ?, company = ? WHERE job_id = ?",
                        (new_title, company or str(row["company"] or ""), job_id),
                    )
                    counts["titles_fixed"] += 1
            else:  # remoteok
                new_title = repair_mojibake(title)
                if new_title != title:
                    conn.execute("UPDATE leads SET title = ? WHERE job_id = ?", (new_title, job_id))
                    counts["titles_fixed"] += 1
                cleaned = strip_remoteok_noise(repair_mojibake(description))
                # Stored descriptions never contain blank lines (strip_html_text
                # removed them at scrape time), so collapsing the gap the strip
                # leaves behind is safe and keeps the pass idempotent.
                cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
                if cleaned != description:
                    conn.execute("UPDATE leads SET description = ? WHERE job_id = ?", (cleaned, job_id))
                    counts["descriptions_cleaned"] += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    _log.info(
        "stored-lead normalize: titles_fixed=%s descriptions_cleaned=%s",
        counts["titles_fixed"],
        counts["descriptions_cleaned"],
    )
    return counts
