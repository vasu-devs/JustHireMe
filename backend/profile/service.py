from __future__ import annotations
import logging

import asyncio
import re
from collections.abc import Mapping
from typing import Any

from data.graph.connection import run_graph
from data.graph import profile as graph_profile
from data.sqlite import settings


class ProfileService:
    def get_profile(self) -> dict:
        return graph_profile.get_profile()

    def refresh_profile_snapshot(self) -> None:
        graph_profile.refresh_profile_snapshot()

    async def _run_post_ingest_sync(self) -> dict:
        """Rebuild Kuzu correlations and Lance vectors before ingest returns."""
        try:
            return await run_graph(graph_profile.rebuild_profile_correlations)
        except Exception as exc:
            logging.getLogger(__name__).warning('post-ingest profile graph/vector sync skipped: %s', exc)
            return {"status": "skipped", "error": str(exc)}

    def update_candidate(self, name: str, summary: str) -> dict:
        return graph_profile.update_candidate(name, summary)

    def update_identity(self, identity: dict) -> dict:
        return graph_profile.update_identity(identity)

    def add_skill(self, name: str, category: str = "general") -> dict:
        return graph_profile.add_skill(name, category)

    def update_skill(self, skill_id: str, name: str, category: str = "general") -> dict:
        return graph_profile.update_skill(skill_id, name, category)

    def delete_skill(self, skill_id: str) -> None:
        graph_profile.delete_skill(skill_id)

    def add_experience(self, role: str, company: str, period: str, description: str) -> dict:
        return graph_profile.add_experience(role, company, period, description)

    def update_experience(self, experience_id: str, role: str, company: str, period: str, description: str) -> dict:
        return graph_profile.update_experience(experience_id, role, company, period, description)

    def delete_experience(self, experience_id: str) -> None:
        graph_profile.delete_experience(experience_id)

    def add_project(self, title: str, stack: str, repo: str, impact: str) -> dict:
        return graph_profile.add_project(title, stack, repo, impact)

    def update_project(self, project_id: str, title: str, stack: str, repo: str, impact: str) -> dict:
        return graph_profile.update_project(project_id, title, stack, repo, impact)

    def delete_project(self, project_id: str) -> None:
        graph_profile.delete_project(project_id)

    def add_education(self, title: str) -> dict:
        return graph_profile.add_education(title)

    def add_certification(self, title: str) -> dict:
        return graph_profile.add_certification(title)

    def add_achievement(self, title: str) -> dict:
        return graph_profile.add_achievement(title)

    def delete_education(self, entry: str) -> None:
        graph_profile.delete_education(entry)

    def delete_certification(self, entry: str) -> None:
        graph_profile.delete_certification(entry)

    def delete_achievement(self, entry: str) -> None:
        graph_profile.delete_achievement(entry)

    async def ingest_resume(self, raw: str = "", pdf_path: str | None = None):
        from profile.ingestor import ingest

        result = await asyncio.to_thread(ingest, raw, pdf_path)
        snapshot = _profile_snapshot_from_resume(result, await run_graph(self.get_profile))
        if graph_profile.profile_has_data(snapshot):
            await run_graph(graph_profile.forget_profile_deletions_for_profile, snapshot)
            await run_graph(graph_profile.save_profile_snapshot, snapshot)
        await run_graph(self.refresh_profile_snapshot)
        if graph_profile.profile_has_data(snapshot):
            await run_graph(graph_profile.save_profile_snapshot, snapshot)
        await self._run_post_ingest_sync()
        return result

    async def ingest_linkedin(self, zip_bytes: bytes) -> dict:
        from profile.linkedin_parser import parse_linkedin_export
        from profile.normalization import normalize_profile_payload

        parsed = await asyncio.to_thread(parse_linkedin_export, zip_bytes)
        cleaned = normalize_profile_payload({
            "candidate": {"name": parsed["candidate"].get("n", ""), "summary": parsed["candidate"].get("s", "")},
            "skills": [{"name": item.get("n", ""), "category": item.get("cat", "general")} for item in parsed.get("skills", [])],
            "experience": parsed.get("experience", []),
            "education": parsed.get("education", []),
            "projects": parsed.get("projects", []),
            "certifications": parsed.get("certifications", []),
        })
        errors: list[str] = []

        candidate = cleaned["candidate"]
        if candidate["name"]:
            try:
                await run_graph(self.update_candidate, candidate["name"], candidate["summary"])
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', exc)
                errors.append(f"candidate: {exc}")

        for skill in cleaned["skills"]:
            try:
                await run_graph(self.add_skill, skill["name"], skill["category"])
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', log_exc)
                pass

        for exp in cleaned.get("experience", parsed["experience"]):
            try:
                await run_graph(self.add_experience, exp["role"], exp["co"], exp["period"], exp["d"])
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', exc)
                errors.append(f"exp {exp.get('role')}: {exc}")

        for edu in cleaned["education"]:
            try:
                await run_graph(self.add_education, edu["title"])
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', exc)
                errors.append(f"edu: {exc}")

        for project in cleaned["projects"]:
            try:
                await run_graph(self.add_project, project["title"], project["stack"], project["repo"], project["impact"])
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', exc)
                errors.append(f"proj {project.get('title')}: {exc}")

        for cert in cleaned["certifications"]:
            try:
                await run_graph(self.add_certification, cert["title"])
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_linkedin: %s', exc)
                errors.append(f"cert: {exc}")

        sync_status = await self._run_post_ingest_sync()

        return {
            "status": "ok" if not errors else "partial",
            "stats": {**parsed["stats"], "graph_sync": sync_status},
            "location": parsed["location"],
            "errors": errors,
        }

    async def ingest_github(self, username: str, token: str | None = None, max_repos: int = 100) -> dict:
        from profile.github_ingestor import ingest_github
        from profile.normalization import normalize_profile_payload

        result = await ingest_github(username, token=token, max_repos=max_repos)
        if "error" in result:
            return result

        errors = list(result.get("errors", []))
        cleaned = normalize_profile_payload({
            "skills": [{"name": item.get("n", ""), "category": item.get("cat", "github")} for item in result.get("skills", [])],
            "projects": result.get("projects", []),
        })
        result["skills"] = [{"n": item["name"], "cat": item.get("category", "github")} for item in cleaned["skills"]]
        result["projects"] = cleaned["projects"]

        for skill in result["skills"]:
            try:
                await run_graph(self.add_skill, skill["n"], skill["cat"])
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_github: %s', log_exc)
                pass

        for project in result["projects"]:
            try:
                details = project.get("impact") or ""
                description = project.get("description") or ""
                features = project.get("features") or []
                if description and description not in details:
                    details = f"{description}\n\n{details}".strip()
                if features:
                    detail_lines = "\n".join(f"- {item}" for item in features[:6])
                    details = f"{details}\n\nHighlights:\n{detail_lines}".strip()
                await run_graph(self.add_project, project["title"], project["stack"], project["repo"], details)
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:ingest_github: %s', exc)
                errors.append(f"proj {project.get('title')}: {exc}")

        github_user = result.get("github_user", {})
        settings_update: dict[str, str] = {}
        if github_user.get("login"):
            settings_update["github_username"] = github_user["login"]
        if github_user.get("blog"):
            settings_update["website_url"] = github_user["blog"]
        if settings_update:
            await asyncio.to_thread(settings.save_settings, settings_update)

        sync_status = await self._run_post_ingest_sync()

        return {
            "status": "ok" if not errors else "partial",
            "github_user": result["github_user"],
            "stats": {**result["stats"], "graph_sync": sync_status},
            "errors": errors,
        }

    async def ingest_portfolio(self, url: str, auto_import: bool = False) -> dict:
        from profile.portfolio_ingestor import ingest_portfolio_url

        result = await ingest_portfolio_url(url)
        if auto_import and not result.get("error"):
            imported = await self.import_profile_data(result)
            result = {**result, "imported": imported}
        return result

    async def import_profile_data(self, body: Any) -> dict:
        from profile.normalization import normalize_profile_payload_report

        data = _as_dict(body)
        data, import_report = normalize_profile_payload_report(data)
        errors: list[str] = []
        stats = {key: 0 for key in ["skills", "experience", "projects", "education", "certifications", "achievements"]}
        existing_snapshot = await run_graph(self.get_profile)
        imported_snapshot = _profile_snapshot_from_import(data, existing_snapshot)
        if graph_profile.profile_has_data(imported_snapshot):
            await run_graph(graph_profile.forget_profile_deletions_for_profile, imported_snapshot)
            await run_graph(graph_profile.save_profile_snapshot, imported_snapshot)

        with graph_profile.bulk_profile_import():
            candidate = _as_dict(data.get("candidate") or {})
            candidate_name = candidate.get("name", candidate.get("n", ""))
            candidate_summary = candidate.get("summary", candidate.get("s", ""))
            if candidate_name or candidate_summary:
                try:
                    await run_graph(self.update_candidate, candidate_name, candidate_summary)
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"candidate: {exc}")

            identity = _as_dict(data.get("identity") or {})
            identity_map = {
                "email": identity.get("email", ""),
                "phone": identity.get("phone", ""),
                "linkedin_url": identity.get("linkedin_url", ""),
                "github_url": identity.get("github_url", ""),
                "website_url": identity.get("website_url", ""),
                "city": identity.get("city", ""),
            }
            if any(identity_map.values()):
                try:
                    await run_graph(self.update_identity, {key: value for key, value in identity_map.items() if value})
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"identity: {exc}")

            for skill in data.get("skills", []) or []:
                item = _as_dict(skill)
                try:
                    await run_graph(self.add_skill, item.get("name", item.get("n", "")), item.get("category", item.get("cat", "general")))
                    stats["skills"] += 1
                except Exception as log_exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', log_exc)
                    pass

            for exp in data.get("experience", []) or []:
                item = _as_dict(exp)
                role = item.get("role", "")
                try:
                    await run_graph(
                        self.add_experience,
                        role,
                        item.get("company", item.get("co", "")),
                        item.get("period", ""),
                        item.get("description", item.get("d", "")),
                    )
                    stats["experience"] += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"exp {role}: {exc}")

            for project in data.get("projects", []) or []:
                item = _as_dict(project)
                title = item.get("title", "")
                try:
                    await run_graph(self.add_project, title, item.get("stack", ""), item.get("repo", ""), item.get("impact", ""))
                    stats["projects"] += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"proj {title}: {exc}")

            for edu in data.get("education", []) or []:
                title = _entry_title(edu)
                try:
                    await run_graph(self.add_education, title)
                    stats["education"] += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"edu: {exc}")

            for cert in data.get("certifications", []) or []:
                title = _entry_title(cert)
                try:
                    await run_graph(self.add_certification, title)
                    stats["certifications"] += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"cert: {exc}")

            for achievement in data.get("achievements", []) or []:
                title = _entry_title(achievement)
                try:
                    await run_graph(self.add_achievement, title)
                    stats["achievements"] += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                    errors.append(f"achievement: {exc}")

        try:
            await run_graph(self.refresh_profile_snapshot)
        except Exception as exc:
            logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
            errors.append(f"profile refresh: {exc}")

        if graph_profile.profile_has_data(imported_snapshot):
            try:
                await run_graph(graph_profile.save_profile_snapshot, imported_snapshot)
            except Exception as exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/profile/service.py:import_profile_data: %s', exc)
                errors.append(f"profile snapshot fallback: {exc}")

        sync_status = await self._run_post_ingest_sync()
        vector_status = sync_status.get("vectors", sync_status)

        # `imported` reflects what actually reached the graph (stats), not just what
        # normalized — keep the two consistent for the summary.
        import_report["imported"] = {key: stats.get(key, 0) for key in import_report.get("imported", {})}
        summary = _summarize_import(stats, import_report)
        return {
            "status": "ok" if not errors else "partial",
            "stats": {**stats, "vector_sync": vector_status, "graph_sync": sync_status},
            "errors": errors,
            # Additive transparency (existing keys above are unchanged): a one-line
            # human summary + a structured report of received/imported/skipped/capped.
            "summary": summary,
            "report": import_report,
        }


def _as_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


_IMPORT_LABELS = (
    ("skills", "skill", "skills"),
    ("experience", "role", "roles"),
    ("projects", "project", "projects"),
    ("education", "education entry", "education entries"),
    ("certifications", "certification", "certifications"),
    ("achievements", "achievement", "achievements"),
)


def _summarize_import(stats: dict, report: dict) -> str:
    """One-line human summary of an import: what landed, what was skipped, what was
    capped. Clauses with a zero count are omitted."""
    imported = [
        f"{stats[key]} {singular if stats[key] == 1 else plural}"
        for key, singular, plural in _IMPORT_LABELS
        if stats.get(key)
    ]
    head = "Imported " + ", ".join(imported) if imported else "Nothing was imported"
    tails: list[str] = []
    skipped_total = sum(int(item.get("count", 0)) for item in report.get("skipped", []))
    if skipped_total:
        tails.append(f"skipped {skipped_total}")
    for capped in report.get("capped", []):
        tails.append(f"capped {capped['field']} {capped['original']}->{capped['kept']}")
    return head + ("" if not tails else "; " + ", ".join(tails))


def _entry_title(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(_as_dict(value).get("title", ""))


def _profile_snapshot_from_import(data: dict, existing: dict | None = None) -> dict:
    existing = graph_profile.normal_profile(existing)
    incoming = graph_profile.empty_profile()

    candidate = _as_dict(data.get("candidate") or {})
    candidate_name = str(candidate.get("name", candidate.get("n", existing.get("n", ""))) or "")
    candidate_summary = str(candidate.get("summary", candidate.get("s", existing.get("s", ""))) or "")
    incoming["n"] = candidate_name.strip()
    incoming["s"] = candidate_summary.strip()

    incoming["skills"] = [
        {
            "id": graph_profile.hash_id(str(item.get("name", item.get("n", "")) or "").strip()),
            "n": str(item.get("name", item.get("n", "")) or "").strip(),
            "cat": str(item.get("category", item.get("cat", "general")) or "general").strip() or "general",
        }
        for raw in data.get("skills", []) or []
        for item in [_as_dict(raw)]
        if str(item.get("name", item.get("n", "")) or "").strip()
    ]

    incoming["exp"] = [
        {
            "id": graph_profile.hash_id(str(item.get("role", "")) + str(item.get("company", item.get("co", "")))),
            "role": str(item.get("role", "") or "").strip(),
            "co": str(item.get("company", item.get("co", "")) or "").strip(),
            "period": str(item.get("period", "") or "").strip(),
            "d": str(item.get("description", item.get("d", "")) or "").strip(),
        }
        for raw in data.get("experience", []) or []
        for item in [_as_dict(raw)]
        if str(item.get("role", "") or item.get("company", item.get("co", "")) or "").strip()
    ]

    incoming["projects"] = [
        {
            "id": graph_profile.hash_id(str(item.get("title", "") or "").strip()),
            "title": str(item.get("title", "") or "").strip(),
            "stack": graph_profile.stack_list(item.get("stack", "")),
            "repo": str(item.get("repo", "") or "").strip(),
            "impact": str(item.get("impact", "") or "").strip(),
        }
        for raw in data.get("projects", []) or []
        for item in [_as_dict(raw)]
        if str(item.get("title", "") or "").strip()
    ]

    incoming["education"] = [_entry_title(item).strip() for item in data.get("education", []) or [] if _entry_title(item).strip()]
    incoming["certifications"] = [_entry_title(item).strip() for item in data.get("certifications", []) or [] if _entry_title(item).strip()]
    incoming["achievements"] = [_entry_title(item).strip() for item in data.get("achievements", []) or [] if _entry_title(item).strip()]
    incoming_identity = _as_dict(data.get("identity") or {})
    incoming["identity"] = {
        key: str(incoming_identity.get(key) or existing.get("identity", {}).get(key, "") or "").strip()
        for key in graph_profile.IDENTITY_KEYS
    }

    return _merge_profile_snapshots(existing, incoming)


def _profile_snapshot_from_resume(profile: Any, existing: dict | None = None) -> dict:
    data = profile.model_dump() if hasattr(profile, "model_dump") else _as_dict(profile)
    incoming = {
        "candidate": {
            "name": data.get("n", ""),
            "summary": data.get("s", ""),
        },
        "skills": [
            {"name": item.get("n", ""), "category": item.get("cat", "general")}
            for item in data.get("skills", []) or []
            if isinstance(item, dict) and item.get("n")
        ],
        "experience": [
            {
                "role": item.get("role", ""),
                "company": item.get("co", ""),
                "period": item.get("period", ""),
                "description": item.get("d", ""),
            }
            for item in data.get("exp", []) or []
            if isinstance(item, dict)
        ],
        "projects": [
            {
                "title": item.get("title", ""),
                "stack": ", ".join(item.get("stack", []) or []) if isinstance(item.get("stack"), list) else item.get("stack", ""),
                "repo": item.get("repo", "") or "",
                "impact": item.get("impact", ""),
            }
            for item in data.get("projects", []) or []
            if isinstance(item, dict)
        ],
        "education": data.get("education", []) or [],
        "certifications": data.get("certifications", []) or [],
        "achievements": data.get("achievements", []) or [],
    }
    return _profile_snapshot_from_import(incoming, existing)


def _merge_profile_snapshots(existing: dict, incoming: dict) -> dict:
    merged = graph_profile.normal_profile(existing)
    incoming = graph_profile.normal_profile(incoming)
    if incoming.get("n") or incoming.get("s"):
        merged["n"] = incoming.get("n") or merged.get("n", "")
        merged["s"] = incoming.get("s") or merged.get("s", "")
    merged["identity"] = {**(merged.get("identity") or {}), **{k: v for k, v in (incoming.get("identity") or {}).items() if v}}
    for key, id_key in [("skills", "id"), ("projects", "id"), ("exp", "id")]:
        merged[key] = _dedupe_dict_items([*(merged.get(key) or []), *(incoming.get(key) or [])], id_key)
    for key in ["education", "certifications", "achievements"]:
        merged[key] = _dedupe_text_items([*(merged.get(key) or []), *(incoming.get(key) or [])])
    return merged


def _norm_key(value: Any) -> str:
    # Lossy key for free-text items (education/certifications/achievements) where
    # punctuation/spacing variants of the SAME entry should de-duplicate (an entry
    # that differs only in dashes/commas/spacing collapses to one).
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _norm_key_strict(value: Any) -> str:
    # Punctuation-preserving key for skill/project/experience dedup, where tech-name
    # punctuation is significant: collapsing it dropped genuinely-distinct skills
    # (C vs C++ vs C#, .NET vs NET). Matches the [a-z0-9+#.-] class the rest of the
    # codebase treats as significant for skills.
    return re.sub(r"[^a-z0-9+#.-]+", "", str(value or "").lower())


def _dedupe_dict_items(items: list[dict], id_key: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        # Content-based key so the same job/project extracted twice with minor
        # text differences (which produce different id hashes) still de-dupes.
        role = str(item.get("role") or "").strip()
        company = str(item.get("co") or item.get("company") or "").strip()
        if role or company:
            key = _norm_key_strict(f"{role} {company}")
        else:
            # Skills/projects: keep C vs C++ vs C# distinct so a real skill isn't
            # dropped as a false duplicate.
            key = _norm_key_strict(item.get("title") or item.get("n") or item.get(id_key) or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _dedupe_text_items(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = _entry_title(item).strip()
        key = _norm_key(text)
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
