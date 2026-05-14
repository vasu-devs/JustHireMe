from __future__ import annotations

import json
import html
import re

from data.sqlite.connection import DEFAULT_DB_PATH, connect


LEAD_SELECT_COLUMNS = (
    "job_id,title,company,url,platform,status,score,reason,match_points,asset_path,"
    "description,gaps,cover_letter_path,selected_projects,kind,budget,signal_score,"
    "signal_reason,signal_tags,outreach_reply,outreach_dm,source_meta,feedback,"
    "feedback_note,followup_due_at,last_contacted_at,outreach_email,proposal_draft,"
    "fit_bullets,followup_sequence,proof_snippet,tech_stack,location,urgency,"
    "base_signal_score,learning_delta,learning_reason,created_at,resume_version"
)


def json_list(value: str | list) -> list:
    if isinstance(value, list):
        return value
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return [part.strip() for part in raw.split(",") if part.strip()]


def json_dict(value: str | dict) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def json_dumps_list(items: list | str | None) -> str:
    if items is None:
        values = []
    elif isinstance(items, str):
        raw = items.strip()
        if not raw:
            values = []
        elif raw.startswith("["):
            return raw
        else:
            values = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        values = [str(item).strip() for item in items if str(item).strip()]
    return json.dumps(values, ensure_ascii=False)


def lead_row_dict(row) -> dict:
    source_meta = json_dict(row[21] or "{}")
    return {
        "job_id": row[0], "title": row[1], "company": row[2], "url": row[3],
        "platform": row[4], "status": row[5], "score": row[6] or 0,
        "reason": row[7] or "",
        "match_points": json_list(row[8] or "[]"),
        "asset": row[9] or "",
        "description": row[10] or "",
        "gaps": json_list(row[11] or "[]"),
        "resume_asset": row[9] or "",
        "cover_letter_asset": row[12] or "",
        "selected_projects": json_list(row[13] or "[]"),
        "kind": row[14] or "job",
        "budget": row[15] or "",
        "signal_score": row[16] or 0,
        "signal_reason": row[17] or "",
        "signal_tags": json_list(row[18] or "[]"),
        "outreach_reply": row[19] or "",
        "outreach_dm": row[20] or "",
        "source_meta": source_meta,
        "lead_quality_score": source_meta.get("lead_quality_score") or 0,
        "lead_quality_reason": source_meta.get("lead_quality_reason") or "",
        "keyword_coverage": source_meta.get("keyword_coverage") or {},
        "contact_lookup": source_meta.get("contact_lookup") or {},
        "feedback": row[22] or "",
        "feedback_note": row[23] or "",
        "followup_due_at": row[24] or "",
        "last_contacted_at": row[25] or "",
        "outreach_email": row[26] or "",
        "proposal_draft": row[27] or "",
        "fit_bullets": json_list(row[28] or "[]"),
        "followup_sequence": json_list(row[29] or "[]"),
        "proof_snippet": row[30] or "",
        "tech_stack": json_list(row[31] or "[]"),
        "location": row[32] or "",
        "urgency": row[33] or "",
        "base_signal_score": row[34] or 0,
        "learning_delta": row[35] or 0,
        "learning_reason": row[36] or "",
        "created_at": row[37] or "",
        "resume_version": row[38] or 0,
    }


def url_exists(job_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT 1 FROM leads WHERE job_id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    return row is not None


def save_lead(lead: dict, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO leads(
                job_id,title,company,url,platform,description,kind,budget,
                signal_score,signal_reason,signal_tags,outreach_reply,outreach_dm,
                outreach_email,proposal_draft,fit_bullets,followup_sequence,
                proof_snippet,tech_stack,location,urgency,base_signal_score,
                learning_delta,learning_reason,source_meta
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lead.get("job_id") or "",
                lead.get("title") or "",
                lead.get("company") or "",
                lead.get("url") or "",
                lead.get("platform") or "",
                lead.get("description") or "",
                lead.get("kind") or "job",
                lead.get("budget") or "",
                int(lead.get("signal_score") or 0),
                str(lead.get("signal_reason") or "")[:700],
                json_dumps_list(lead.get("signal_tags")),
                lead.get("outreach_reply") or "",
                lead.get("outreach_dm") or "",
                lead.get("outreach_email") or "",
                lead.get("proposal_draft") or "",
                json_dumps_list(lead.get("fit_bullets")),
                json_dumps_list(lead.get("followup_sequence")),
                lead.get("proof_snippet") or "",
                json_dumps_list(lead.get("tech_stack")),
                lead.get("location") or "",
                lead.get("urgency") or "",
                int(lead.get("base_signal_score") or lead.get("signal_score") or 0),
                int(lead.get("learning_delta") or 0),
                str(lead.get("learning_reason") or "")[:700],
                json.dumps(lead.get("source_meta") or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_leads(db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {LEAD_SELECT_COLUMNS} FROM leads ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [lead_row_dict(row) for row in rows]


def get_feedback_training_examples(limit: int = 300, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT feedback,platform,company,kind,signal_tags,tech_stack,source_meta,
                   location,urgency,budget,title,description
            FROM leads
            WHERE feedback != ''
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 300), 1000)),),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "feedback": row[0] or "",
            "platform": row[1] or "",
            "company": row[2] or "",
            "kind": row[3] or "job",
            "signal_tags": json_list(row[4] or "[]"),
            "tech_stack": json_list(row[5] or "[]"),
            "source_meta": json_dict(row[6] or "{}"),
            "location": row[7] or "",
            "urgency": row[8] or "",
            "budget": row[9] or "",
            "title": row[10] or "",
            "description": row[11] or "",
        }
        for row in rows
    ]


def get_leads_for_learning(limit: int = 500, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT {LEAD_SELECT_COLUMNS}
            FROM leads
            WHERE feedback = '' AND status != 'discarded'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 500), 1000)),),
        ).fetchall()
    finally:
        conn.close()
    return [lead_row_dict(row) for row in rows]


def update_learning_score(job_id: str, ranked: dict, base_signal_score: int, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE leads
            SET signal_score=?, signal_reason=?, source_meta=?, base_signal_score=?,
                learning_delta=?, learning_reason=?
            WHERE job_id=?
            """,
            (
                int(ranked.get("signal_score") or 0),
                str(ranked.get("signal_reason") or "")[:700],
                json.dumps(ranked.get("source_meta") or {}, ensure_ascii=False),
                int(ranked.get("base_signal_score") or base_signal_score),
                int(ranked.get("learning_delta") or 0),
                str(ranked.get("learning_reason") or "")[:700],
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_text(lead: dict) -> str:
    parts = [
        lead.get("title", ""),
        lead.get("company", ""),
        lead.get("platform", ""),
        lead.get("url", ""),
        lead.get("description", ""),
        lead.get("reason", ""),
        lead.get("signal_reason", ""),
    ]
    text = html.unescape("\n".join(str(part or "") for part in parts))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def looks_like_cleanup_hn_job(text: str) -> bool:
    clean = cleanup_text({"description": text})
    if len(clean) < 80:
        return False
    first_line = clean.splitlines()[0].lower()
    lower = clean.lower()
    role_terms = (
        "engineer", "developer", "software", "backend", "front-end", "frontend",
        "full-stack", "full stack", "devops", "sre", "data", "analyst",
        "designer", "product", "security", "machine learning", "ml", "ai",
        "research", "infrastructure", "platform", "mobile", "ios", "android",
        "qa", "support", "solutions", "sales", "marketing", "operations",
        "founding",
    )
    hiring_terms = (
        "remote", "onsite", "on-site", "hybrid", "visa", "salary", "apply",
        "full-time", "part-time", "contract", "intern", "hiring", "equity",
        "location", "relocation",
    )
    has_role = any(term in lower for term in role_terms)
    has_hiring_signal = any(term in lower for term in hiring_terms)
    explicit_hiring = any(
        phrase in lower
        for phrase in ("we are hiring", "we're hiring", "is hiring", "are hiring", "hiring for")
    )
    return (first_line.count("|") >= 2 and has_role and has_hiring_signal) or (has_role and has_hiring_signal and explicit_hiring)


def lead_cleanup_reasons(lead: dict) -> list[str]:
    text = cleanup_text(lead)
    lower = text.lower()
    title = str(lead.get("title") or "").strip()
    title_lower = title.lower()
    platform = str(lead.get("platform") or "").lower()
    url = str(lead.get("url") or "").lower()
    reasons: list[str] = []

    if not title:
        reasons.append("missing title")
    if not str(lead.get("url") or "").strip():
        reasons.append("missing source url")

    if title_lower.startswith(("ask hn:", "show hn:", "tell hn:", "launch hn:")) and "who is hiring" not in title_lower:
        reasons.append("HN story/commentary title, not a job")

    is_hn = platform in {"hn", "hackernews", "hn_hiring"} or "news.ycombinator.com/item?id=" in url
    if is_hn and not looks_like_cleanup_hn_job(text):
        reasons.append("HN item does not match a job-posting pattern")

    discussion_terms = (
        "maybe ", "i think", "why ", "what ", "how ", "should ", "deprecate",
        "tutorial", "blog post", "newsletter", "podcast", "comment thread",
        "this thread", "discussion", "upvote", "downvote", "karma",
    )
    hiring_terms = (
        "apply", "hiring", "full-time", "part-time", "contract", "salary",
        "equity", "remote", "onsite", "hybrid", "visa", "recruiter",
    )
    if any(term in lower for term in discussion_terms) and not any(term in lower for term in hiring_terms):
        reasons.append("discussion/tutorial content without hiring signal")

    return sorted(set(reasons))


def cleanup_bad_leads(limit: int = 1000, dry_run: bool = False, db_path: str = DEFAULT_DB_PATH) -> dict:
    limit = max(1, min(int(limit or 1000), 5000))
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT {LEAD_SELECT_COLUMNS}
            FROM leads
            WHERE status NOT IN ('approved','applied','interviewing','rejected','accepted','discarded','completed')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        touched: list[dict] = []
        for row in rows:
            lead = lead_row_dict(row)
            reasons = lead_cleanup_reasons(lead)
            if not reasons:
                continue

            note = "DB cleanup: " + "; ".join(reasons)
            touched.append({
                "job_id": lead["job_id"],
                "title": lead.get("title", ""),
                "company": lead.get("company", ""),
                "platform": lead.get("platform", ""),
                "reasons": reasons,
            })
            if dry_run:
                continue
            conn.execute(
                """
                UPDATE leads
                SET status='discarded', feedback='incorrect_category', feedback_note=?
                WHERE job_id=?
                """,
                (note[:1000], lead["job_id"]),
            )
            conn.execute(
                "INSERT INTO events(job_id,action) VALUES(?,?)",
                (lead["job_id"], note[:1000]),
            )

        conn.commit()
    finally:
        conn.close()
    return {"scanned": len(rows), "discarded": 0 if dry_run else len(touched), "candidates": len(touched), "dry_run": dry_run, "items": touched}


def update_lead_score(
    job_id: str,
    score: int,
    reason: str,
    match_points: list | None = None,
    gaps: list | None = None,
    preserve_status: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT kind,status FROM leads WHERE job_id=?", (job_id,)).fetchone()
        kind = row[0] if row else "job"
        current_status = row[1] if row and row[1] else "discovered"

        if preserve_status:
            status = current_status
        elif kind == "freelance":
            status = "matched" if score >= 76 else "discarded"
        else:
            status = "tailoring" if score >= 76 else "discarded"

        if preserve_status:
            conn.execute(
                "UPDATE leads SET score=?, reason=?, match_points=?, gaps=? WHERE job_id=?",
                (score, reason[:500], json_dumps_list(match_points), json_dumps_list(gaps), job_id),
            )
        else:
            conn.execute(
                "UPDATE leads SET status=?, score=?, reason=?, match_points=?, gaps=? WHERE job_id=?",
                (status, score, reason[:500], json_dumps_list(match_points), json_dumps_list(gaps), job_id),
            )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"score={score} status={'preserved:' if preserve_status else ''}{status}"),
        )
        conn.commit()
    finally:
        conn.close()


def update_lead_status(job_id: str, status: str, db_path: str = DEFAULT_DB_PATH) -> None:
    valid = {
        "discovered", "evaluating", "tailoring", "approved",
        "applied", "interviewing", "rejected", "accepted", "discarded",
        "matched", "bidding", "proposal_sent", "awarded", "completed",
    }
    if status not in valid:
        raise ValueError(f"Invalid status: {status}")
    conn = connect(db_path)
    try:
        cur = conn.execute("UPDATE leads SET status=? WHERE job_id=?", (status, job_id))
        if getattr(cur, "rowcount", 0) == 0:
            raise LookupError(f"lead {job_id!r} not found")
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"status_changed={status}"),
        )
        conn.commit()
    finally:
        conn.close()


def save_asset_path(job_id: str, path: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE leads SET status='approved', asset_path=? WHERE job_id=?",
            (path, job_id),
        )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"asset={path}"),
        )
        conn.commit()
    finally:
        conn.close()


def save_asset_package(
    job_id: str,
    resume_path: str,
    cover_letter_path: str = "",
    selected_projects: list | None = None,
    keyword_coverage: dict | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = connect(db_path)
    try:
        meta_row = conn.execute("SELECT source_meta FROM leads WHERE job_id=?", (job_id,)).fetchone()
        source_meta = json_dict(meta_row[0] if meta_row else "{}")
        if keyword_coverage:
            source_meta["keyword_coverage"] = keyword_coverage
        conn.execute(
            "UPDATE leads SET status='approved', asset_path=?, cover_letter_path=?, selected_projects=?, source_meta=? WHERE job_id=?",
            (
                resume_path,
                cover_letter_path,
                json.dumps(selected_projects or []),
                json.dumps(source_meta, ensure_ascii=False),
                job_id,
            ),
        )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"assets=resume:{resume_path} cover:{cover_letter_path}"),
        )
        conn.commit()
    finally:
        conn.close()


def get_resume_version(job_id: str, db_path: str = DEFAULT_DB_PATH) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT resume_version FROM leads WHERE job_id = ?", (job_id,)).fetchone()
    finally:
        conn.close()
    return int(row[0] or 0) if row else 0


def save_generated_asset_version(
    job_id: str,
    resume_path: str,
    cover_letter_path: str,
    resume_version: int,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            UPDATE leads
            SET asset_path = ?, cover_letter_path = ?, resume_version = ?
            WHERE job_id = ?
            """,
            (resume_path, cover_letter_path, int(resume_version or 0), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_contact_lookup(job_id: str, contact_lookup: dict | None, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT source_meta FROM leads WHERE job_id=?", (job_id,)).fetchone()
        source_meta = json_dict(row[0] if row else "{}")
        source_meta["contact_lookup"] = contact_lookup or {"status": "empty", "contacts": []}
        conn.execute(
            "UPDATE leads SET source_meta=? WHERE job_id=?",
            (json.dumps(source_meta, ensure_ascii=False), job_id),
        )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"contact_lookup={source_meta['contact_lookup'].get('status', 'unknown')}"),
        )
        conn.commit()
    finally:
        conn.close()


def update_outreach_fields(job_id: str, fields: dict[str, str], db_path: str = DEFAULT_DB_PATH) -> None:
    allowed = {"outreach_reply", "outreach_dm", "outreach_email", "proposal_draft"}
    payload = {key: str(value or "") for key, value in fields.items() if key in allowed}
    if not payload:
        return
    conn = connect(db_path)
    try:
        sets = ", ".join(f"{key}=?" for key in payload)
        vals = list(payload.values()) + [job_id]
        conn.execute(f"UPDATE leads SET {sets} WHERE job_id=?", vals)
        conn.commit()
    finally:
        conn.close()


def mark_applied(job_id: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        conn.execute("UPDATE leads SET status='applied' WHERE job_id=?", (job_id,))
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, "submitted application"),
        )
        conn.commit()
    finally:
        conn.close()


def save_lead_feedback(
    job_id: str,
    feedback: str,
    note: str = "",
    contacted_at: str = "",
    followup_due_at: str = "",
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    valid = {
        "good", "trash", "too_generic", "not_ai",
        "not_freelance", "already_contacted",
        "relevant", "not_relevant", "duplicate",
        "low_quality", "incorrect_category",
    }
    if feedback not in valid:
        raise ValueError(f"Invalid feedback: {feedback}")

    conn = connect(db_path)
    try:
        row = conn.execute("SELECT kind,status FROM leads WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return {}

        kind = row[0] or "job"
        status = row[1] or "discovered"
        new_status = status
        if feedback in {
            "trash", "too_generic", "not_ai", "not_freelance",
            "not_relevant", "duplicate", "low_quality", "incorrect_category",
        }:
            new_status = "discarded"
        elif feedback == "already_contacted":
            new_status = "proposal_sent" if kind == "freelance" else "applied"

        conn.execute(
            "UPDATE leads SET feedback=?, feedback_note=?, status=?, last_contacted_at=COALESCE(NULLIF(?, ''), last_contacted_at), followup_due_at=COALESCE(NULLIF(?, ''), followup_due_at) WHERE job_id=?",
            (feedback, note or "", new_status, contacted_at, followup_due_at, job_id),
        )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"feedback={feedback}"),
        )
        conn.commit()
    finally:
        conn.close()
    return get_lead_by_id(job_id, db_path)


def update_lead_followup(
    job_id: str,
    contacted_at: str,
    followup_due_at: str,
    db_path: str = DEFAULT_DB_PATH,
) -> dict:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT 1 FROM leads WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return {}
        conn.execute(
            "UPDATE leads SET followup_due_at=?, last_contacted_at=COALESCE(NULLIF(last_contacted_at, ''), ?) WHERE job_id=?",
            (followup_due_at, contacted_at, job_id),
        )
        conn.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (job_id, f"followup_due={followup_due_at}"),
        )
        conn.commit()
    finally:
        conn.close()
    return get_lead_by_id(job_id, db_path)


def get_all_freelance_leads(db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {LEAD_SELECT_COLUMNS} FROM leads WHERE kind='freelance' ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [lead_row_dict(row) for row in rows]


def get_job_leads_for_evaluation(db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT {LEAD_SELECT_COLUMNS}
            FROM leads
            WHERE COALESCE(NULLIF(kind, ''), 'job')='job'
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [lead_row_dict(row) for row in rows]


def get_lead_by_id(job_id: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        row = conn.execute(
            f"SELECT {LEAD_SELECT_COLUMNS} FROM leads WHERE job_id=?",
            (job_id,),
        ).fetchone()
        events = conn.execute(
            "SELECT action, ts FROM events WHERE job_id=? ORDER BY ts DESC LIMIT 20",
            (job_id,),
        ).fetchall()
    finally:
        conn.close()
    if not row:
        return {}
    lead = lead_row_dict(row)
    lead["events"] = [{"action": event[0], "ts": event[1]} for event in events]
    return lead


def get_lead_for_fire_base(job_id: str, db_path: str = DEFAULT_DB_PATH) -> tuple[dict, str]:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT job_id,title,company,url,platform,status,score,reason,match_points,asset_path,description,gaps,cover_letter_path,selected_projects,kind,budget FROM leads WHERE job_id=?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {}, ""

    path = row[9] or ""
    cover_path = row[12] or ""
    lead = {
        "job_id": row[0], "title": row[1], "company": row[2], "url": row[3],
        "platform": row[4], "status": row[5], "score": row[6] or 0,
        "reason": row[7] or "",
        "match_points": json_list(row[8] or "[]"),
        "asset": path,
        "resume_asset": path,
        "asset_path": path,
        "description": row[10] or "",
        "gaps": json_list(row[11] or "[]"),
        "cover_letter_asset": cover_path,
        "cover_letter_path": cover_path,
        "selected_projects": json_list(row[13] or "[]"),
        "kind": row[14] or "job",
        "budget": row[15] or "",
    }
    return lead, path


def get_lead_for_fire(job_id: str, db_path: str = DEFAULT_DB_PATH) -> tuple[dict, str]:
    return get_lead_for_fire_base(job_id, db_path=db_path)


def delete_lead(job_id: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        cur = conn.execute("DELETE FROM leads WHERE job_id=?", (job_id,))
        if getattr(cur, "rowcount", 0) == 0:
            raise LookupError(f"lead {job_id!r} not found")
        conn.execute("DELETE FROM events WHERE job_id=?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def get_due_followups(limit: int = 25, now: str = "", db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT {LEAD_SELECT_COLUMNS}
            FROM leads
            WHERE followup_due_at != '' AND followup_due_at <= ? AND status != 'discarded'
            ORDER BY followup_due_at ASC
            LIMIT ?
            """,
            (now, max(1, min(int(limit or 25), 100))),
        ).fetchall()
    finally:
        conn.close()
    return [lead_row_dict(row) for row in rows]


def get_discovered_leads(db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT job_id,title,company,url,platform,description FROM leads WHERE status='discovered' AND COALESCE(NULLIF(kind, ''), 'job')='job'"
        ).fetchall()
    finally:
        conn.close()
    return [
        {"job_id": row[0], "title": row[1], "company": row[2], "url": row[3], "platform": row[4], "description": row[5] or ""}
        for row in rows
    ]


def get_discovered_freelance_leads(db_path: str = DEFAULT_DB_PATH) -> list:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT job_id,title,company,url,platform,description,budget FROM leads WHERE status='discovered' AND kind='freelance'"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "job_id": row[0],
            "title": row[1],
            "company": row[2],
            "url": row[3],
            "platform": row[4],
            "description": row[5] or "",
            "budget": row[6] or "",
        }
        for row in rows
    ]
