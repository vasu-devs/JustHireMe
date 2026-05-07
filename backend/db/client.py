import os
import sys
import sqlite3 as _sq
import json
from datetime import UTC, datetime, timedelta
import kuzu
import lancedb
from logger import get_logger

_log = get_logger(__name__)


def _data_dir() -> str:
    """Return the platform-appropriate data directory for JustHireMe.

    Windows : %LOCALAPPDATA%/JustHireMe
    macOS   : ~/Library/Application Support/JustHireMe
    Linux   : ~/.local/share/justhireme
    Fallback: ~/.justhireme
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "JustHireMe")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "JustHireMe")
    base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(base, "justhireme")


_b = _data_dir()
_g, _v = os.path.join(_b, "graph"), os.path.join(_b, "vector")
sql = os.path.join(_b, "crm.db")


def _utc_timestamp(offset: timedelta | None = None) -> str:
    value = datetime.now(UTC)
    if offset is not None:
        value += offset
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _NullVectorStore:
    """No-op vector store so profile CRUD never fails because embeddings are unavailable."""

    def list_tables(self):
        return []

    def create_table(self, *_args, **_kwargs):
        return None

    def open_table(self, *_args, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None


def _ensure_dir(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception as exc:
        alt = f"{path}_store"
        try:
            os.makedirs(alt, exist_ok=True)
            _log.warning("storage path unavailable (%s: %s); using %s", path, exc, alt)
            return alt
        except Exception as alt_exc:
            _log.error("storage path unavailable (%s: %s; fallback: %s)", path, exc, alt_exc)
            return path


_b = _ensure_dir(_b)
_g, _v = os.path.join(_b, "graph"), os.path.join(_b, "vector")
_v = _ensure_dir(_v)

db   = kuzu.Database(_g)
conn = kuzu.Connection(db)
try:
    vec: lancedb.LanceDBConnection | _NullVectorStore = lancedb.connect(_v)
except Exception as exc:
    _log.warning("vector store disabled: %s", exc)
    vec = _NullVectorStore()

def _init():
    for s in [
        "CREATE NODE TABLE IF NOT EXISTS Candidate(id STRING, n STRING, s STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Skill(id STRING, n STRING, cat STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Project(id STRING, title STRING, stack STRING, repo STRING, impact STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Experience(id STRING, role STRING, co STRING, period STRING, d STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Certification(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Education(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS Achievement(id STRING, title STRING, PRIMARY KEY(id))",
        "CREATE NODE TABLE IF NOT EXISTS JobLead(job_id STRING, title STRING, co STRING, url STRING, platform STRING, PRIMARY KEY(job_id))",
        "CREATE REL TABLE IF NOT EXISTS WORKED_AS(FROM Candidate TO Experience)",
        "CREATE REL TABLE IF NOT EXISTS BUILT(FROM Candidate TO Project)",
        "CREATE REL TABLE IF NOT EXISTS HAS_CERTIFICATION(FROM Candidate TO Certification)",
        "CREATE REL TABLE IF NOT EXISTS HAS_EDUCATION(FROM Candidate TO Education)",
        "CREATE REL TABLE IF NOT EXISTS HAS_ACHIEVEMENT(FROM Candidate TO Achievement)",
        "CREATE REL TABLE IF NOT EXISTS EXP_UTILIZES(FROM Experience TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS PROJ_UTILIZES(FROM Project TO Skill)",
        "CREATE REL TABLE IF NOT EXISTS REQUIRES(FROM JobLead TO Skill)",
    ]:
        conn.execute(s)

_init()


def _init_sql():
    c = _sq.connect(sql)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS leads(
            job_id TEXT PRIMARY KEY, title TEXT, company TEXT,
            url TEXT, platform TEXT, status TEXT DEFAULT 'discovered',
            score INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            match_points TEXT DEFAULT '',
            asset_path TEXT DEFAULT '',
            cover_letter_path TEXT DEFAULT '',
            selected_projects TEXT DEFAULT '',
            description TEXT DEFAULT '',
            gaps TEXT DEFAULT '',
            resume_version INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT, action TEXT, ts TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, val TEXT
        );
    """)
    # Migration: add columns if upgrading from older schema
    for col, definition in [
        ("score",        "INTEGER DEFAULT 0"),
        ("reason",       "TEXT DEFAULT ''"),
        ("match_points", "TEXT DEFAULT ''"),
        ("asset_path",   "TEXT DEFAULT ''"),
        ("cover_letter_path", "TEXT DEFAULT ''"),
        ("selected_projects", "TEXT DEFAULT ''"),
        ("description",  "TEXT DEFAULT ''"),
        ("gaps",         "TEXT DEFAULT ''"),
        ("kind",         "TEXT DEFAULT 'job'"),
        ("budget",       "TEXT DEFAULT ''"),
        ("signal_score", "INTEGER DEFAULT 0"),
        ("signal_reason", "TEXT DEFAULT ''"),
        ("signal_tags", "TEXT DEFAULT ''"),
        ("outreach_reply", "TEXT DEFAULT ''"),
        ("outreach_dm", "TEXT DEFAULT ''"),
        ("source_meta", "TEXT DEFAULT ''"),
        ("feedback", "TEXT DEFAULT ''"),
        ("feedback_note", "TEXT DEFAULT ''"),
        ("followup_due_at", "TEXT DEFAULT ''"),
        ("last_contacted_at", "TEXT DEFAULT ''"),
        ("outreach_email", "TEXT DEFAULT ''"),
        ("proposal_draft", "TEXT DEFAULT ''"),
        ("fit_bullets", "TEXT DEFAULT ''"),
        ("followup_sequence", "TEXT DEFAULT ''"),
        ("proof_snippet", "TEXT DEFAULT ''"),
        ("tech_stack", "TEXT DEFAULT ''"),
        ("location", "TEXT DEFAULT ''"),
        ("urgency", "TEXT DEFAULT ''"),
        ("base_signal_score", "INTEGER DEFAULT 0"),
        ("learning_delta", "INTEGER DEFAULT 0"),
        ("learning_reason", "TEXT DEFAULT ''"),
        ("resume_version", "INTEGER DEFAULT 0"),
    ]:
        try:
            c.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
        except Exception:
            pass  # column already exists
    try:
        c.execute("ALTER TABLE leads ADD COLUMN resume_version INTEGER DEFAULT 0")
        c.commit()
    except Exception:
        pass  # column already exists
    c.commit()
    c.close()

_init_sql()


_LEAD_SELECT_COLUMNS = (
    "job_id,title,company,url,platform,status,score,reason,match_points,asset_path,"
    "description,gaps,cover_letter_path,selected_projects,kind,budget,signal_score,"
    "signal_reason,signal_tags,outreach_reply,outreach_dm,source_meta,feedback,"
    "feedback_note,followup_due_at,last_contacted_at,outreach_email,proposal_draft,"
    "fit_bullets,followup_sequence,proof_snippet,tech_stack,location,urgency,"
    "base_signal_score,learning_delta,learning_reason,created_at,resume_version"
)


def record_event(job_id: str | None, action: str):
    c = _sq.connect(sql)
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        ((job_id or "__system__")[:160], str(action or "")[:1000]),
    )
    c.commit()
    c.close()


def url_exists(jid: str) -> bool:
    c = _sq.connect(sql)
    r = c.execute("SELECT 1 FROM leads WHERE job_id=?", (jid,)).fetchone()
    c.close()
    return r is not None


def save_lead(
    jid: str,
    t: str,
    co: str,
    u: str,
    plat: str,
    desc: str = "",
    kind: str = "job",
    budget: str = "",
    signal_score: int = 0,
    signal_reason: str = "",
    signal_tags: list | None = None,
    outreach_reply: str = "",
    outreach_dm: str = "",
    outreach_email: str = "",
    proposal_draft: str = "",
    fit_bullets: list | str | None = None,
    followup_sequence: list | str | None = None,
    proof_snippet: str = "",
    tech_stack: list | str | None = None,
    location: str = "",
    urgency: str = "",
    base_signal_score: int | None = None,
    learning_delta: int | None = None,
    learning_reason: str = "",
    source_meta: dict | None = None,
):
    lead = {
        "job_id": jid,
        "title": t,
        "company": co,
        "url": u,
        "platform": plat,
        "description": desc,
        "kind": kind or "job",
        "budget": budget or "",
        "signal_score": int(signal_score or 0),
        "signal_reason": signal_reason or "",
        "signal_tags": signal_tags or [],
        "outreach_reply": outreach_reply or "",
        "outreach_dm": outreach_dm or "",
        "outreach_email": outreach_email or "",
        "proposal_draft": proposal_draft or "",
        "fit_bullets": fit_bullets or [],
        "followup_sequence": followup_sequence or [],
        "proof_snippet": proof_snippet or "",
        "tech_stack": tech_stack or [],
        "location": location or "",
        "urgency": urgency or "",
        "source_meta": source_meta or {},
    }
    if base_signal_score is None and learning_delta is None and not learning_reason:
        lead = rank_lead_by_feedback(lead)
    else:
        lead["base_signal_score"] = int(base_signal_score if base_signal_score is not None else signal_score or 0)
        lead["learning_delta"] = int(learning_delta or 0)
        lead["learning_reason"] = learning_reason or ""

    c = _sq.connect(sql)
    c.execute(
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
            jid, t, co, u, plat, desc, lead.get("kind") or "job", lead.get("budget") or "",
            int(lead.get("signal_score") or 0), str(lead.get("signal_reason") or "")[:700],
            _json_dumps_list(lead.get("signal_tags")),
            lead.get("outreach_reply") or "", lead.get("outreach_dm") or "",
            lead.get("outreach_email") or "", lead.get("proposal_draft") or "",
            _json_dumps_list(lead.get("fit_bullets")),
            _json_dumps_list(lead.get("followup_sequence")),
            lead.get("proof_snippet") or "",
            _json_dumps_list(lead.get("tech_stack")),
            lead.get("location") or "", lead.get("urgency") or "",
            int(lead.get("base_signal_score") or lead.get("signal_score") or 0),
            int(lead.get("learning_delta") or 0),
            str(lead.get("learning_reason") or "")[:700],
            json.dumps(lead.get("source_meta") or {}, ensure_ascii=False),
        ),
    )
    c.commit()
    c.close()


def update_lead_score(
    jid: str,
    s: int,
    r: str,
    match_points: list | None = None,
    gaps: list | None = None,
    preserve_status: bool = False,
):
    c = _sq.connect(sql)
    row = c.execute("SELECT kind,status FROM leads WHERE job_id=?", (jid,)).fetchone()
    kind = row[0] if row else "job"
    current_status = row[1] if row and row[1] else "discovered"

    if preserve_status:
        status = current_status
    elif kind == "freelance":
        status = "matched" if s >= 76 else "discarded"
    else:
        status = "tailoring" if s >= 76 else "discarded"

    mp  = _json_dumps_list(match_points)
    gps = _json_dumps_list(gaps)
    if preserve_status:
        c.execute(
            "UPDATE leads SET score=?, reason=?, match_points=?, gaps=? WHERE job_id=?",
            (s, r[:500], mp, gps, jid),
        )
    else:
        c.execute(
            "UPDATE leads SET status=?, score=?, reason=?, match_points=?, gaps=? WHERE job_id=?",
            (status, s, r[:500], mp, gps, jid),
        )
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"score={s} status={'preserved:' if preserve_status else ''}{status}"),
    )
    c.commit()
    c.close()


def save_asset_path(jid: str, path: str):
    c = _sq.connect(sql)
    c.execute(
        "UPDATE leads SET status='approved', asset_path=? WHERE job_id=?",
        (path, jid),
    )
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"asset={path}"),
    )
    c.commit()
    c.close()


def save_asset_package(
    jid: str,
    resume_path: str,
    cover_letter_path: str = "",
    selected_projects: list | None = None,
    keyword_coverage: dict | None = None,
):
    projects = json.dumps(selected_projects or [])
    c = _sq.connect(sql)
    meta_row = c.execute("SELECT source_meta FROM leads WHERE job_id=?", (jid,)).fetchone()
    source_meta = _json_dict(meta_row[0] if meta_row else "{}")
    if keyword_coverage:
        source_meta["keyword_coverage"] = keyword_coverage
    c.execute(
        "UPDATE leads SET status='approved', asset_path=?, cover_letter_path=?, selected_projects=?, source_meta=? WHERE job_id=?",
        (resume_path, cover_letter_path, projects, json.dumps(source_meta, ensure_ascii=False), jid),
    )
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"assets=resume:{resume_path} cover:{cover_letter_path}"),
    )
    c.commit()
    c.close()


def save_contact_lookup(jid: str, contact_lookup: dict | None):
    c = _sq.connect(sql)
    row = c.execute("SELECT source_meta FROM leads WHERE job_id=?", (jid,)).fetchone()
    source_meta = _json_dict(row[0] if row else "{}")
    source_meta["contact_lookup"] = contact_lookup or {"status": "empty", "contacts": []}
    c.execute(
        "UPDATE leads SET source_meta=? WHERE job_id=?",
        (json.dumps(source_meta, ensure_ascii=False), jid),
    )
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"contact_lookup={source_meta['contact_lookup'].get('status', 'unknown')}"),
    )
    c.commit()
    c.close()


def mark_applied(jid: str):
    c = _sq.connect(sql)
    c.execute("UPDATE leads SET status='applied' WHERE job_id=?", (jid,))
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, "submitted application"),
    )
    c.commit()
    c.close()


def get_all_leads() -> list:
    c = _sq.connect(sql)
    rows = c.execute(
        f"SELECT {_LEAD_SELECT_COLUMNS} FROM leads ORDER BY created_at DESC"
    ).fetchall()
    c.close()
    return [_lead_row_dict(r) for r in rows]


def _lead_row_dict(r) -> dict:
    source_meta = _json_dict(r[21] or "{}")
    return {
        "job_id": r[0], "title": r[1], "company": r[2], "url": r[3],
        "platform": r[4], "status": r[5], "score": r[6] or 0,
        "reason": r[7] or "",
        "match_points": _json_list(r[8] or "[]"),
        "asset": r[9] or "",
        "description": r[10] or "",
        "gaps": _json_list(r[11] or "[]"),
        "resume_asset": r[9] or "",
        "cover_letter_asset": r[12] or "",
        "selected_projects": _json_list(r[13] or "[]"),
        "kind": r[14] or "job",
        "budget": r[15] or "",
        "signal_score": r[16] or 0,
        "signal_reason": r[17] or "",
        "signal_tags": _json_list(r[18] or "[]"),
        "outreach_reply": r[19] or "",
        "outreach_dm": r[20] or "",
        "source_meta": source_meta,
        "lead_quality_score": source_meta.get("lead_quality_score") or 0,
        "lead_quality_reason": source_meta.get("lead_quality_reason") or "",
        "keyword_coverage": source_meta.get("keyword_coverage") or {},
        "contact_lookup": source_meta.get("contact_lookup") or {},
        "feedback": r[22] or "",
        "feedback_note": r[23] or "",
        "followup_due_at": r[24] or "",
        "last_contacted_at": r[25] or "",
        "outreach_email": r[26] or "",
        "proposal_draft": r[27] or "",
        "fit_bullets": _json_list(r[28] or "[]"),
        "followup_sequence": _json_list(r[29] or "[]"),
        "proof_snippet": r[30] or "",
        "tech_stack": _json_list(r[31] or "[]"),
        "location": r[32] or "",
        "urgency": r[33] or "",
        "base_signal_score": r[34] or 0,
        "learning_delta": r[35] or 0,
        "learning_reason": r[36] or "",
        "created_at": r[37] or "",
        "resume_version": r[38] or 0,
    }


def get_all_freelance_leads() -> list:
    c = _sq.connect(sql)
    rows = c.execute(
        f"SELECT {_LEAD_SELECT_COLUMNS} FROM leads WHERE kind='freelance' ORDER BY created_at DESC"
    ).fetchall()
    c.close()
    return [_lead_row_dict(r) for r in rows]


def get_job_leads_for_evaluation() -> list:
    c = _sq.connect(sql)
    rows = c.execute(
        f"""
        SELECT {_LEAD_SELECT_COLUMNS}
        FROM leads
        WHERE COALESCE(NULLIF(kind, ''), 'job')='job'
        ORDER BY created_at DESC
        """
    ).fetchall()
    c.close()
    return [_lead_row_dict(r) for r in rows]


def _json_list(s: str) -> list:
    if isinstance(s, list):
        return s
    raw = str(s or "").strip()
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        return [p.strip() for p in raw.split(",") if p.strip()]


def _json_dumps_list(items: list | None) -> str:
    if items is None:
        values = []
    elif isinstance(items, str):
        raw = items.strip()
        if not raw:
            values = []
        elif raw.startswith("["):
            return raw
        else:
            values = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        values = [str(x).strip() for x in items if str(x).strip()]
    return json.dumps(values, ensure_ascii=False)


def _json_dict(s: str) -> dict:
    if isinstance(s, dict):
        return s
    try:
        v = json.loads(str(s or "{}"))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _cleanup_text(lead: dict) -> str:
    import html
    import re

    parts = [
        lead.get("title", ""),
        lead.get("company", ""),
        lead.get("platform", ""),
        lead.get("url", ""),
        lead.get("description", ""),
        lead.get("reason", ""),
        lead.get("signal_reason", ""),
    ]
    text = html.unescape("\n".join(str(p or "") for p in parts))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _looks_like_cleanup_hn_job(text: str) -> bool:
    clean = _cleanup_text({"description": text})
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
    text = _cleanup_text(lead)
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
    if is_hn and not _looks_like_cleanup_hn_job(text):
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


def cleanup_bad_leads(limit: int = 1000, dry_run: bool = False) -> dict:
    limit = max(1, min(int(limit or 1000), 5000))
    c = _sq.connect(sql)
    rows = c.execute(
        f"""
        SELECT {_LEAD_SELECT_COLUMNS}
        FROM leads
        WHERE status NOT IN ('approved','applied','interviewing','accepted','completed')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    touched: list[dict] = []
    for row in rows:
        lead = _lead_row_dict(row)
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
        c.execute(
            """
            UPDATE leads
            SET status='discarded', feedback='incorrect_category', feedback_note=?
            WHERE job_id=?
            """,
            (note[:1000], lead["job_id"]),
        )
        c.execute(
            "INSERT INTO events(job_id,action) VALUES(?,?)",
            (lead["job_id"], note[:1000]),
        )

    c.commit()
    c.close()
    return {"scanned": len(rows), "discarded": 0 if dry_run else len(touched), "candidates": len(touched), "dry_run": dry_run, "items": touched}


def get_feedback_training_examples(limit: int = 300) -> list[dict]:
    c = _sq.connect(sql)
    rows = c.execute(
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
    c.close()
    return [
        {
            "feedback": r[0] or "",
            "platform": r[1] or "",
            "company": r[2] or "",
            "kind": r[3] or "job",
            "signal_tags": _json_list(r[4] or "[]"),
            "tech_stack": _json_list(r[5] or "[]"),
            "source_meta": _json_dict(r[6] or "{}"),
            "location": r[7] or "",
            "urgency": r[8] or "",
            "budget": r[9] or "",
            "title": r[10] or "",
            "description": r[11] or "",
        }
        for r in rows
    ]


def rank_lead_by_feedback(lead: dict) -> dict:
    try:
        from agents.feedback_ranker import apply_feedback_learning
        return apply_feedback_learning(lead, get_feedback_training_examples())
    except Exception:
        out = dict(lead)
        out.setdefault("base_signal_score", int(out.get("signal_score") or 0))
        out.setdefault("learning_delta", 0)
        out.setdefault("learning_reason", "")
        return out


def _without_learning_suffix(reason: str) -> str:
    import re
    return re.sub(r"(?:;\s*)?feedback learning [+-]\d+", "", reason or "").strip(" ;")


def recompute_learning_scores(limit: int = 500) -> int:
    try:
        from agents.feedback_ranker import apply_feedback_learning
    except Exception:
        return 0

    examples = get_feedback_training_examples()
    if not examples:
        return 0

    c = _sq.connect(sql)
    rows = c.execute(
        f"""
        SELECT {_LEAD_SELECT_COLUMNS}
        FROM leads
        WHERE feedback = '' AND status != 'discarded'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 500), 1000)),),
    ).fetchall()

    updated = 0
    for row in rows:
        lead = _lead_row_dict(row)
        base = int(lead.get("base_signal_score") or lead.get("signal_score") or 0)
        lead["signal_score"] = base
        lead["signal_reason"] = _without_learning_suffix(lead.get("signal_reason", ""))
        ranked = apply_feedback_learning(lead, examples)
        c.execute(
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
                int(ranked.get("base_signal_score") or base),
                int(ranked.get("learning_delta") or 0),
                str(ranked.get("learning_reason") or "")[:700],
                lead["job_id"],
            ),
        )
        updated += 1
    c.commit()
    c.close()
    return updated


def _read_pdf_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _pick_first_line(text: str) -> str:
    for line in (text or "").splitlines():
        value = line.strip()
        if value and len(value) <= 80 and "@" not in value and "http" not in value.lower():
            return value
    return ""


def _contact_from_text(text: str) -> dict:
    import re

    email = ""
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    if m:
        email = m.group(0)

    phone = ""
    m = re.search(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,5}\d{2,4}", text or "")
    if m:
        phone = m.group(0).strip()

    urls = re.findall(r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s),;]*)?", text or "")
    linkedin = next((u for u in urls if "linkedin.com" in u.lower()), "")
    github = next((u for u in urls if "github.com" in u.lower()), "")
    website = next((u for u in urls if u not in {linkedin, github} and "@" not in u), "")

    def norm_url(u: str) -> str:
        if not u:
            return ""
        return u if u.startswith(("http://", "https://")) else f"https://{u}"

    return {
        "email": email,
        "phone": phone,
        "linkedin_url": norm_url(linkedin),
        "github": norm_url(github),
        "website": norm_url(website or github or linkedin),
    }


def get_lead_for_fire(jid: str) -> tuple:
    c = _sq.connect(sql)
    row = c.execute(
        "SELECT job_id,title,company,url,platform,status,score,reason,match_points,asset_path,description,gaps,cover_letter_path,selected_projects,kind,budget FROM leads WHERE job_id=?",
        (jid,)
    ).fetchone()
    c.close()
    if not row:
        return {}, ""

    path = row[9] or ""
    cover_path = row[12] or ""
    try:
        profile = get_profile()
    except Exception:
        profile = {}
    resume_text = _read_pdf_text(path)
    cover_text = _read_pdf_text(cover_path)
    try:
        settings = get_settings()
    except Exception:
        settings = {}
    contact = _contact_from_text("\n".join([
        resume_text,
        cover_text,
        profile.get("s", ""),
        "\n".join(str(p.get("repo", "")) for p in profile.get("projects", [])),
    ]))

    name = (profile.get("n") or settings.get("candidate_name") or _pick_first_line(resume_text)).strip()
    parts = name.split()
    first_name = parts[0] if parts else ""
    last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    lead = {
        "job_id": row[0], "title": row[1], "company": row[2], "url": row[3],
        "platform": row[4], "status": row[5], "score": row[6] or 0,
        "reason": row[7] or "",
        "match_points": _json_list(row[8] or "[]"),
        "asset": path,
        "resume_asset": path,
        "asset_path": path,
        "description": row[10] or "",
        "gaps": _json_list(row[11] or "[]"),
        "cover_letter_asset": cover_path,
        "cover_letter_path": cover_path,
        "selected_projects": _json_list(row[13] or "[]"),
        "kind": row[14] or "job",
        "budget": row[15] or "",
        "profile": profile,
        "name": name,
        "candidate_name": name,
        "first_name": settings.get("first_name") or first_name,
        "last_name": settings.get("last_name") or last_name,
        "email": settings.get("candidate_email") or settings.get("email") or contact["email"],
        "phone": settings.get("candidate_phone") or settings.get("phone") or contact["phone"],
        "linkedin_url": settings.get("linkedin_url") or settings.get("candidate_linkedin") or contact["linkedin_url"],
        "website": settings.get("website") or settings.get("portfolio_url") or contact["website"],
        "github": settings.get("github") or settings.get("github_url") or contact["github"],
        "cover_letter": cover_text.strip(),
    }
    return lead, path


def save_settings(d: dict):
    c = _sq.connect(sql)
    for k, v in d.items():
        c.execute("INSERT OR REPLACE INTO settings(key,val) VALUES(?,?)", (k, str(v)))
    c.commit()
    c.close()


def get_settings() -> dict:
    c = _sq.connect(sql)
    rows = c.execute("SELECT key,val FROM settings").fetchall()
    c.close()
    return {r[0]: r[1] for r in rows}


def get_setting(k: str, default: str = "") -> str:
    c = _sq.connect(sql)
    r = c.execute("SELECT val FROM settings WHERE key=?", (k,)).fetchone()
    c.close()
    return r[0] if r else default


def get_lead_by_id(jid: str) -> dict:
    c = _sq.connect(sql)
    row = c.execute(
        f"SELECT {_LEAD_SELECT_COLUMNS} FROM leads WHERE job_id=?",
        (jid,)
    ).fetchone()
    evs = c.execute(
        "SELECT action, ts FROM events WHERE job_id=? ORDER BY ts DESC LIMIT 20",
        (jid,)
    ).fetchall()
    c.close()
    if not row:
        return {}
    lead = _lead_row_dict(row)
    lead["events"] = [{"action": e[0], "ts": e[1]} for e in evs]
    return lead


def delete_lead(jid: str):
    c = _sq.connect(sql)
    cur = c.execute("DELETE FROM leads WHERE job_id=?", (jid,))
    if getattr(cur, "rowcount", 0) == 0:
        c.close()
        raise LookupError(f"lead {jid!r} not found")
    c.execute("DELETE FROM events WHERE job_id=?", (jid,))
    c.commit()
    c.close()


def update_lead_status(jid: str, status: str):
    valid = {
        "discovered", "evaluating", "tailoring", "approved",
        "applied", "interviewing", "rejected", "accepted", "discarded",
        "matched", "bidding", "proposal_sent", "awarded", "completed",
    }
    if status not in valid:
        raise ValueError(f"Invalid status: {status}")
    c = _sq.connect(sql)
    cur = c.execute("UPDATE leads SET status=? WHERE job_id=?", (status, jid))
    if getattr(cur, "rowcount", 0) == 0:
        c.close()
        raise LookupError(f"lead {jid!r} not found")
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"status_changed={status}"),
    )
    c.commit()
    c.close()


def save_lead_feedback(jid: str, feedback: str, note: str = "") -> dict:
    valid = {
        "good", "trash", "too_generic", "not_ai",
        "not_freelance", "already_contacted",
        "relevant", "not_relevant", "duplicate",
        "low_quality", "incorrect_category",
    }
    if feedback not in valid:
        raise ValueError(f"Invalid feedback: {feedback}")

    c = _sq.connect(sql)
    row = c.execute("SELECT kind,status FROM leads WHERE job_id=?", (jid,)).fetchone()
    if not row:
        c.close()
        return {}

    kind = row[0] or "job"
    status = row[1] or "discovered"
    new_status = status
    now = ""
    due = ""
    if feedback in {
        "trash", "too_generic", "not_ai", "not_freelance",
        "not_relevant", "duplicate", "low_quality", "incorrect_category",
    }:
        new_status = "discarded"
    elif feedback == "already_contacted":
        now = _utc_timestamp()
        due = _utc_timestamp(timedelta(days=5))
        new_status = "proposal_sent" if kind == "freelance" else "applied"

    c.execute(
        "UPDATE leads SET feedback=?, feedback_note=?, status=?, last_contacted_at=COALESCE(NULLIF(?, ''), last_contacted_at), followup_due_at=COALESCE(NULLIF(?, ''), followup_due_at) WHERE job_id=?",
        (feedback, note or "", new_status, now, due, jid),
    )
    c.execute(
        "INSERT INTO events(job_id,action) VALUES(?,?)",
        (jid, f"feedback={feedback}"),
    )
    c.commit()
    c.close()
    recompute_learning_scores()
    return get_lead_by_id(jid)


def update_lead_followup(jid: str, days: int = 5) -> dict:
    days = max(1, min(int(days or 5), 60))
    due = _utc_timestamp(timedelta(days=days))
    now = _utc_timestamp()
    c = _sq.connect(sql)
    row = c.execute("SELECT 1 FROM leads WHERE job_id=?", (jid,)).fetchone()
    if not row:
        c.close()
        return {}
    c.execute(
        "UPDATE leads SET followup_due_at=?, last_contacted_at=COALESCE(NULLIF(last_contacted_at, ''), ?) WHERE job_id=?",
        (due, now, jid),
    )
    c.execute("INSERT INTO events(job_id,action) VALUES(?,?)", (jid, f"followup_due={due}"))
    c.commit()
    c.close()
    return get_lead_by_id(jid)


def get_due_followups(limit: int = 25) -> list:
    now = _utc_timestamp()
    c = _sq.connect(sql)
    rows = c.execute(
        """
        SELECT {columns}
        FROM leads
        WHERE followup_due_at != '' AND followup_due_at <= ? AND status != 'discarded'
        ORDER BY followup_due_at ASC
        LIMIT ?
        """.format(columns=_LEAD_SELECT_COLUMNS),
        (now, max(1, min(int(limit or 25), 100))),
    ).fetchall()
    c.close()
    return [_lead_row_dict(r) for r in rows]


def get_events(limit: int = 100, job_id: str | None = None) -> list:
    c = _sq.connect(sql)
    if job_id:
        rows = c.execute(
            "SELECT job_id,action,ts FROM events WHERE job_id=? ORDER BY ts DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT job_id,action,ts FROM events ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    c.close()
    return [{"job_id": r[0], "action": r[1], "ts": r[2]} for r in rows]


def get_discovered_leads() -> list:
    c = _sq.connect(sql)
    rows = c.execute(
        "SELECT job_id,title,company,url,platform,description FROM leads WHERE status='discovered' AND COALESCE(NULLIF(kind, ''), 'job')='job'"
    ).fetchall()
    c.close()
    return [{"job_id": r[0], "title": r[1], "company": r[2], "url": r[3], "platform": r[4], "description": r[5] or ""} for r in rows]


def get_discovered_freelance_leads() -> list:
    c = _sq.connect(sql)
    rows = c.execute(
        "SELECT job_id,title,company,url,platform,description,budget FROM leads WHERE status='discovered' AND kind='freelance'"
    ).fetchall()
    c.close()
    return [
        {
            "job_id": r[0], "title": r[1], "company": r[2],
            "url": r[3], "platform": r[4],
            "description": r[5] or "", "budget": r[6] or "",
        }
        for r in rows
    ]


def _h(t: str) -> str:
    import hashlib
    return hashlib.md5(t.encode()).hexdigest()[:12]


_PROFILE_SNAPSHOT_KEY = "profile_snapshot_json"


def _stack_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _profile_has_data(profile: dict | None) -> bool:
    if not isinstance(profile, dict):
        return False
    return bool(
        str(profile.get("n") or "").strip()
        or str(profile.get("s") or "").strip()
        or profile.get("skills")
        or profile.get("projects")
        or profile.get("exp")
        or profile.get("certifications")
        or profile.get("education")
        or profile.get("achievements")
    )


def _empty_profile() -> dict:
    return {
        "n": "",
        "s": "",
        "skills": [],
        "projects": [],
        "exp": [],
        "certifications": [],
        "education": [],
        "achievements": [],
    }


def _normal_profile(profile: dict | None) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    return {
        "n": str(profile.get("n") or ""),
        "s": str(profile.get("s") or ""),
        "skills": list(profile.get("skills") or []),
        "projects": list(profile.get("projects") or []),
        "exp": list(profile.get("exp") or []),
        "certifications": list(profile.get("certifications") or profile.get("certs") or []),
        "education": list(profile.get("education") or []),
        "achievements": list(profile.get("achievements") or profile.get("awards") or []),
    }


def _load_profile_snapshot() -> dict:
    try:
        c = _sq.connect(sql)
        row = c.execute("SELECT val FROM settings WHERE key=?", (_PROFILE_SNAPSHOT_KEY,)).fetchone()
        c.close()
        if not row:
            return {}
        profile = _normal_profile(json.loads(row[0] or "{}"))
        return profile if _profile_has_data(profile) else {}
    except Exception:
        return {}


def _save_profile_snapshot(profile: dict):
    profile = _normal_profile(profile)
    if not _profile_has_data(profile):
        return
    try:
        c = _sq.connect(sql)
        c.execute(
            "INSERT OR REPLACE INTO settings(key,val) VALUES(?,?)",
            (_PROFILE_SNAPSHOT_KEY, json.dumps(profile, ensure_ascii=False)),
        )
        c.commit()
        c.close()
    except Exception:
        pass


def _read_profile_from_graph() -> dict:
    from kuzu import Connection
    c = Connection(db)

    # 1. Candidate
    r = c.execute("MATCH (n:Candidate) RETURN n.id, n.n, n.s")
    candidates = []
    while r.has_next():
        candidates.append(r.get_next())
    if candidates:
        candidates.sort(
            key=lambda row: (
                0 if str(row[1] or "").strip().lower() in {"", "unknown", "candidate"} else 1,
                len(str(row[1] or "")) + len(str(row[2] or "")),
            ),
            reverse=True,
        )
        cand = candidates[0]
    else:
        cand = ["", "", ""]

    # 2. Skills
    r = c.execute("MATCH (n:Skill) RETURN n.id, n.n, n.cat")
    skills = []
    while r.has_next():
        row = r.get_next()
        skills.append({"id": row[0], "n": row[1], "cat": row[2]})

    # 3. Projects
    r = c.execute("MATCH (n:Project) RETURN n.id, n.title, n.stack, n.repo, n.impact")
    projects = []
    while r.has_next():
        row = r.get_next()
        projects.append({"id": row[0], "title": row[1], "stack": _stack_list(row[2]), "repo": row[3], "impact": row[4]})

    # 4. Experience
    r = c.execute("MATCH (n:Experience) RETURN n.id, n.role, n.co, n.period, n.d")
    exp = []
    while r.has_next():
        row = r.get_next()
        exp.append({"id": row[0], "role": row[1], "co": row[2], "period": row[3], "d": row[4]})

    def _read_text_nodes(label: str) -> list[str]:
        try:
            res = c.execute(f"MATCH (n:{label}) RETURN n.title")
        except Exception:
            return []
        items: list[str] = []
        while res.has_next():
            row = res.get_next()
            text = str(row[0] or "").strip()
            if text:
                items.append(text)
        return items

    return {
        "n": cand[1],
        "s": cand[2],
        "skills": skills,
        "projects": projects,
        "exp": exp,
        "certifications": _read_text_nodes("Certification"),
        "education": _read_text_nodes("Education"),
        "achievements": _read_text_nodes("Achievement"),
    }


def get_profile() -> dict:
    snapshot = _load_profile_snapshot()
    try:
        profile = _normal_profile(_read_profile_from_graph())
    except Exception as exc:
        if snapshot:
            return snapshot
        _log.error("profile read failed: %s", exc)
        return _empty_profile()

    if _profile_has_data(profile):
        _save_profile_snapshot(profile)
        return profile
    return snapshot or profile


def refresh_profile_snapshot():
    try:
        _save_profile_snapshot(_read_profile_from_graph())
    except Exception:
        pass


# ── CRUD: Skills ──────────────────────────────────────────────────

def add_skill(n: str, cat: str) -> dict:
    from kuzu import Connection
    n = str(n or "").strip()
    cat = str(cat or "general").strip() or "general"
    sid = _h(n)
    c = Connection(db)
    try:
        c.execute("CREATE (:Skill {id: $id, n: $n, cat: $cat})", {"id": sid, "n": n, "cat": cat})
    except Exception:
        c = Connection(db)
        c.execute("MATCH (s:Skill) WHERE s.id = $id SET s.n = $n, s.cat = $cat", {"id": sid, "n": n, "cat": cat})
    # Link to candidate if one exists
    c2 = Connection(db)
    try:
        c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
    except Exception:
        pass
    # Add to vector store
    try:
        _add_skill_vec(sid, n, cat)
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": sid, "n": n, "cat": cat}


def update_skill(sid: str, n: str, cat: str) -> dict:
    from kuzu import Connection
    n = str(n or "").strip()
    cat = str(cat or "general").strip() or "general"
    c = Connection(db)
    c.execute("MATCH (s:Skill) WHERE s.id = $id SET s.n = $n, s.cat = $cat", {"id": sid, "n": n, "cat": cat})
    try:
        _add_skill_vec(sid, n, cat)
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": sid, "n": n, "cat": cat}


def delete_skill(sid: str):
    from kuzu import Connection
    _delete_vec_rows("skills", [sid])
    c = Connection(db)
    c.execute("MATCH (s:Skill) WHERE s.id = $id DETACH DELETE s", {"id": sid})
    refresh_profile_snapshot()


# ── CRUD: Experience ──────────────────────────────────────────────

def add_experience(role: str, co: str, period: str, d: str) -> dict:
    from kuzu import Connection
    role = str(role or "").strip()
    co = str(co or "").strip()
    period = str(period or "").strip()
    d = str(d or "").strip()
    eid = _h(role + co)
    c = Connection(db)
    try:
        c.execute(
            "CREATE (:Experience {id: $id, role: $role, co: $co, period: $period, d: $d})",
            {"id": eid, "role": role, "co": co, "period": period, "d": d}
        )
    except Exception:
        c = Connection(db)
        c.execute(
            "MATCH (e:Experience) WHERE e.id = $id SET e.role = $role, e.co = $co, e.period = $period, e.d = $d",
            {"id": eid, "role": role, "co": co, "period": period, "d": d}
        )
    # Link to candidate
    c2 = Connection(db)
    try:
        r = c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        if r.has_next():
            cid = r.get_next()[0]
            c3 = Connection(db)
            c3.execute(
                "MATCH (a:Candidate {id: $s}), (b:Experience {id: $d}) MERGE (a)-[:WORKED_AS]->(b)",
                {"s": cid, "d": eid}
            )
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": eid, "role": role, "co": co, "period": period, "d": d}


def update_experience(eid: str, role: str, co: str, period: str, d: str) -> dict:
    from kuzu import Connection
    role = str(role or "").strip()
    co = str(co or "").strip()
    period = str(period or "").strip()
    d = str(d or "").strip()
    c = Connection(db)
    c.execute(
        "MATCH (e:Experience) WHERE e.id = $id SET e.role = $role, e.co = $co, e.period = $period, e.d = $d",
        {"id": eid, "role": role, "co": co, "period": period, "d": d}
    )
    refresh_profile_snapshot()
    return {"id": eid, "role": role, "co": co, "period": period, "d": d}


def delete_experience(eid: str):
    from kuzu import Connection
    refresh_profile_snapshot()
    c = Connection(db)
    c.execute("MATCH (e:Experience) WHERE e.id = $id DETACH DELETE e", {"id": eid})
    refresh_profile_snapshot()


# ── CRUD: Projects ────────────────────────────────────────────────

def add_project(title: str, stack: str, repo: str, impact: str) -> dict:
    from kuzu import Connection
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    pid = _h(title)
    c = Connection(db)
    try:
        c.execute(
            "CREATE (:Project {id: $id, title: $title, stack: $stack, repo: $repo, impact: $impact})",
            {"id": pid, "title": title, "stack": stack, "repo": repo, "impact": impact}
        )
    except Exception:
        c = Connection(db)
        c.execute(
            "MATCH (p:Project) WHERE p.id = $id SET p.title = $title, p.stack = $stack, p.repo = $repo, p.impact = $impact",
            {"id": pid, "title": title, "stack": stack, "repo": repo, "impact": impact}
        )
    # Link to candidate
    c2 = Connection(db)
    try:
        r = c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        if r.has_next():
            cid = r.get_next()[0]
            c3 = Connection(db)
            c3.execute(
                "MATCH (a:Candidate {id: $s}), (b:Project {id: $d}) MERGE (a)-[:BUILT]->(b)",
                {"s": cid, "d": pid}
            )
    except Exception:
        pass
    # Add to vector store
    try:
        _add_project_vec(pid, title, stack, impact)
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": pid, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def update_project(pid: str, title: str, stack: str, repo: str, impact: str) -> dict:
    from kuzu import Connection
    title = str(title or "").strip()
    stack = str(stack or "").strip()
    repo = str(repo or "").strip()
    impact = str(impact or "").strip()
    c = Connection(db)
    c.execute(
        "MATCH (p:Project) WHERE p.id = $id SET p.title = $title, p.stack = $stack, p.repo = $repo, p.impact = $impact",
        {"id": pid, "title": title, "stack": stack, "repo": repo, "impact": impact}
    )
    try:
        _add_project_vec(pid, title, stack, impact)
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": pid, "title": title, "stack": stack.split(",") if stack else [], "repo": repo, "impact": impact}


def delete_project(pid: str):
    from kuzu import Connection
    _delete_vec_rows("projects", [pid])
    c = Connection(db)
    c.execute("MATCH (p:Project) WHERE p.id = $id DETACH DELETE p", {"id": pid})
    refresh_profile_snapshot()


# ── CRUD: Education ───────────────────────────────────────────────

def add_education(title: str) -> dict:
    from kuzu import Connection
    title = str(title or "").strip()
    eid = _h(title)
    c = Connection(db)
    try:
        c.execute("CREATE (:Education {id: $id, title: $title})", {"id": eid, "title": title})
    except Exception:
        pass  # already exists
    c2 = Connection(db)
    try:
        r = c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        if r.has_next():
            cid = r.get_next()[0]
            c3 = Connection(db)
            c3.execute(
                "MATCH (a:Candidate {id: $s}), (b:Education {id: $d}) MERGE (a)-[:HAS_EDUCATION]->(b)",
                {"s": cid, "d": eid},
            )
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": eid, "title": title}


# ── CRUD: Certification ───────────────────────────────────────────

def add_certification(title: str) -> dict:
    from kuzu import Connection
    title = str(title or "").strip()
    cid_node = _h(title)
    c = Connection(db)
    try:
        c.execute("CREATE (:Certification {id: $id, title: $title})", {"id": cid_node, "title": title})
    except Exception:
        pass  # already exists
    c2 = Connection(db)
    try:
        r = c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        if r.has_next():
            cand_id = r.get_next()[0]
            c3 = Connection(db)
            c3.execute(
                "MATCH (a:Candidate {id: $s}), (b:Certification {id: $d}) MERGE (a)-[:HAS_CERTIFICATION]->(b)",
                {"s": cand_id, "d": cid_node},
            )
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": cid_node, "title": title}


# ── CRUD: Achievements ─────────────────────────────────────────────

def add_achievement(title: str) -> dict:
    from kuzu import Connection
    title = str(title or "").strip()
    aid = _h(title)
    c = Connection(db)
    try:
        c.execute("CREATE (:Achievement {id: $id, title: $title})", {"id": aid, "title": title})
    except Exception:
        pass  # already exists
    c2 = Connection(db)
    try:
        r = c2.execute("MATCH (c:Candidate) RETURN c.id LIMIT 1")
        if r.has_next():
            cand_id = r.get_next()[0]
            c3 = Connection(db)
            c3.execute(
                "MATCH (a:Candidate {id: $s}), (b:Achievement {id: $d}) MERGE (a)-[:HAS_ACHIEVEMENT]->(b)",
                {"s": cand_id, "d": aid},
            )
    except Exception:
        pass
    refresh_profile_snapshot()
    return {"id": aid, "title": title}


# ── CRUD: Candidate ──────────────────────────────────────────────

def update_candidate(name: str, summary: str) -> dict:
    from kuzu import Connection
    import hashlib
    name = str(name or "").strip()
    summary = str(summary or "").strip()
    refresh_profile_snapshot()
    c = Connection(db)
    r = c.execute("MATCH (n:Candidate) RETURN n.id LIMIT 1")
    if r.has_next():
        cid = r.get_next()[0]
        c2 = Connection(db)
        c2.execute(
            "MATCH (n:Candidate {id: $id}) SET n.n = $n, n.s = $s",
            {"id": cid, "n": name, "s": summary}
        )
    else:
        cid = hashlib.md5(name.encode()).hexdigest()[:12]
        c2 = Connection(db)
        try:
            c2.execute(
                "CREATE (:Candidate {id: $id, n: $n, s: $s})",
                {"id": cid, "n": name, "s": summary}
            )
        except Exception:
            pass
    refresh_profile_snapshot()
    return {"n": name, "s": summary}


# ── Vector helpers (reuse ingestor patterns) ──────────────────────

def _delete_vec_rows(table_name: str, ids: list[str]):
    ids = [str(item or "").strip() for item in ids if str(item or "").strip()]
    if not ids:
        return
    try:
        if table_name not in vec.list_tables():
            return
        quoted = ["'" + item.replace("'", "''") + "'" for item in ids]
        vec.open_table(table_name).delete("id IN (" + ", ".join(quoted) + ")")
    except Exception:
        pass


def _add_skill_vec(sid: str, n: str, cat: str):
    try:
        from agents.ingestor import _emb
        vecs = _emb([n])
        if vecs:
            rows = [{"id": sid, "n": n, "cat": cat, "vector": vecs[0]}]
            if "skills" in vec.list_tables():
                _delete_vec_rows("skills", [sid])
                vec.open_table("skills").add(rows)
            else:
                vec.create_table("skills", data=rows)
    except Exception:
        pass


def _add_project_vec(pid: str, title: str, stack: str, impact: str):
    try:
        from agents.ingestor import _emb
        text = f"{title} {stack} {impact}"
        vecs = _emb([text])
        if vecs:
            rows = [{"id": pid, "title": title, "stack": stack, "impact": impact, "vector": vecs[0]}]
            if "projects" in vec.list_tables():
                _delete_vec_rows("projects", [pid])
                vec.open_table("projects").add(rows)
            else:
                vec.create_table("projects", data=rows)
    except Exception:
        pass
