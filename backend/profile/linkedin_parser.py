from __future__ import annotations
import csv
import io
import zipfile
from core.logging import get_logger

_log = get_logger(__name__)


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """Find and parse a CSV by filename pattern (case-insensitive)."""
    candidates = [n for n in zf.namelist()
                  if n.lower().endswith(name.lower())]
    if not candidates:
        _log.warning("linkedin export: %s not found in ZIP", name)
        return []
    with zf.open(candidates[0]) as f:
        text = f.read().decode("utf-8-sig")   # handles BOM
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def parse_linkedin_export(zip_bytes: bytes) -> dict:
    """
    Parse a LinkedIn data export ZIP.
    Returns:
      {
        "candidate": {"n": str, "s": str},
        "skills": [{"n": str, "cat": str}],
        "experience": [{"role": str, "co": str, "period": str, "d": str}],
        "education": [{"title": str}],
        "projects": [{"title": str, "stack": str, "repo": str, "impact": str}],
        "certifications": [{"title": str}],
        "stats": {"skills": int, "experience": int, ...}
      }
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Profile
        profile_rows = _read_csv(zf, "Profile.csv")
        p = profile_rows[0] if profile_rows else {}
        first    = p.get("First Name", "").strip()
        last     = p.get("Last Name", "").strip()
        name     = f"{first} {last}".strip()
        headline = p.get("Headline", "").strip()
        summary  = p.get("Summary", "").strip()
        location = p.get("Geo Location", "").strip()
        candidate_summary = headline
        if summary and summary != headline:
            candidate_summary = f"{headline}\n\n{summary}" if headline else summary

        # Skills
        skill_rows = _read_csv(zf, "Skills.csv")
        skills = []
        for row in skill_rows:
            n = (row.get("Name") or "").strip()
            if n:
                skills.append({"n": n, "cat": "general"})

        # Experience / Positions
        pos_rows = _read_csv(zf, "Positions.csv")
        experience = []
        for row in pos_rows:
            role  = (row.get("Title") or "").strip()
            co    = (row.get("Company Name") or "").strip()
            start = (row.get("Started On") or "").strip()
            end   = (row.get("Finished On") or "Present").strip() or "Present"
            desc  = (row.get("Description") or "").strip()
            loc   = (row.get("Location") or "").strip()
            if role or co:
                period = f"{start} – {end}" if start else end
                d = desc
                if loc:
                    d = f"{d}\n{loc}".strip() if d else loc
                experience.append({"role": role, "co": co, "period": period, "d": d})

        # Education
        edu_rows = _read_csv(zf, "Education.csv")
        education = []
        for row in edu_rows:
            school = (row.get("School Name") or "").strip()
            degree = (row.get("Degree Name") or "").strip()
            notes  = (row.get("Notes") or "").strip()
            start  = (row.get("Start Date") or "").strip()
            end    = (row.get("End Date") or "").strip()
            if school:
                parts = [part for part in [degree, school, notes] if part]
                period = f"{start}–{end}" if start or end else ""
                title  = " · ".join(parts)
                if period:
                    title = f"{title} ({period})"
                education.append({"title": title})

        # Projects
        proj_rows = _read_csv(zf, "Projects.csv")
        projects = []
        for row in proj_rows:
            title = (row.get("Title") or "").strip()
            desc  = (row.get("Description") or "").strip()
            url   = (row.get("Url") or "").strip()
            if title:
                projects.append({
                    "title":  title,
                    "stack":  "",
                    "repo":   url,
                    "impact": desc,
                })

        # Certifications
        cert_rows = _read_csv(zf, "Certifications.csv")
        certifications = []
        for row in cert_rows:
            name_c    = (row.get("Name") or "").strip()
            authority = (row.get("Authority") or "").strip()
            if name_c:
                title = f"{name_c} — {authority}" if authority else name_c
                certifications.append({"title": title})

    return {
        "candidate":      {"n": name, "s": candidate_summary},
        "skills":         skills,
        "experience":     experience,
        "education":      education,
        "projects":       projects,
        "certifications": certifications,
        "location":       location,
        "stats": {
            "skills":         len(skills),
            "experience":     len(experience),
            "education":      len(education),
            "projects":       len(projects),
            "certifications": len(certifications),
        },
    }
