#!/usr/bin/env python3
"""
Seed Adnane Saber's profile into the JustHireMe graph database.

Usage:
    python -m backend.scripts.seed_profile [--check]
    cd backend && python scripts/seed_profile.py

--check   Only verify the profile exists, don't write.
--force   Overwrite existing profile.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure backend is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from data.graph import profile as graph_profile


def _load_template() -> dict:
    template_path = os.path.join(os.path.dirname(__file__), "..", "profiles", "adnane.json")
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


def profile_exists() -> bool:
    """Check if a profile with meaningful data already exists."""
    existing = graph_profile.get_profile()
    return graph_profile.profile_has_data(existing) and bool(str(existing.get("n") or "").strip())


def seed_profile() -> dict:
    """Seed Adnane's profile into the graph DB. Returns summary stats."""
    template = _load_template()
    stats = {
        "candidate": False,
        "skills": 0,
        "experience": 0,
        "projects": 0,
        "education": 0,
        "certifications": 0,
        "achievements": 0,
        "identity": False,
    }

    # Candidate
    name = str(template.get("n") or "").strip()
    summary = str(template.get("s") or "").strip()
    if name or summary:
        graph_profile.update_candidate(name, summary)
        stats["candidate"] = True

    # Identity
    identity = template.get("identity") or {}
    if any(str(v or "").strip() for v in identity.values()):
        graph_profile.update_identity(identity)
        stats["identity"] = True

    # Skills
    for skill in template.get("skills", []) or []:
        if isinstance(skill, dict) and str(skill.get("n") or "").strip():
            graph_profile.add_skill(skill["n"], skill.get("cat", "general"))
            stats["skills"] += 1

    # Experience
    for exp in template.get("exp", []) or []:
        if isinstance(exp, dict):
            role = str(exp.get("role") or "").strip()
            company = str(exp.get("co") or "").strip()
            if role or company:
                graph_profile.add_experience(role, company, exp.get("period", ""), exp.get("d", ""))
                stats["experience"] += 1

    # Projects
    for project in template.get("projects", []) or []:
        if isinstance(project, dict) and str(project.get("title") or "").strip():
            stack = project.get("stack", [])
            if isinstance(stack, list):
                stack = ", ".join(stack)
            graph_profile.add_project(
                project["title"],
                stack,
                project.get("repo", ""),
                project.get("impact", ""),
            )
            stats["projects"] += 1

    # Education
    for edu in template.get("education", []) or []:
        text = str(edu or "").strip()
        if text:
            graph_profile.add_education(text)
            stats["education"] += 1

    # Certifications
    for cert in template.get("certifications", []) or []:
        text = str(cert or "").strip()
        if text:
            graph_profile.add_certification(text)
            stats["certifications"] += 1

    # Achievements
    for ach in template.get("achievements", []) or []:
        text = str(ach or "").strip()
        if text:
            graph_profile.add_achievement(text)
            stats["achievements"] += 1

    # Refresh snapshot + sync vectors
    graph_profile.refresh_profile_snapshot()
    try:
        graph_profile.sync_vectors_from_graph()
    except Exception:
        pass

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Adnane's profile into JustHireMe")
    parser.add_argument("--check", action="store_true", help="Only check if profile exists")
    parser.add_argument("--force", action="store_true", help="Overwrite existing profile")
    args = parser.parse_args()

    has_profile = profile_exists()

    if args.check:
        if has_profile:
            print("Profile already exists.")
            return 0
        print("No profile found.")
        return 1

    if has_profile and not args.force:
        print("Profile already exists. Use --force to overwrite, or --check to verify.")
        return 0

    print(f"{'Overwriting' if has_profile else 'Seeding'} profile...")
    stats = seed_profile()
    print(f"Done! Candidate: {stats['candidate']}, Skills: {stats['skills']}, "
          f"Experience: {stats['experience']}, Projects: {stats['projects']}, "
          f"Education: {stats['education']}, Certifications: {stats['certifications']}, "
          f"Achievements: {stats['achievements']}, Identity: {stats['identity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
