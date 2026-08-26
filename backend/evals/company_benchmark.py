"""Build and validate the Phase-0 company benchmark from existing seed inventories.

Generated entries are crawl candidates, not reviewed coverage evidence.  Their
``review_status`` stays ``needs_review`` until a human confirms company identity,
cohort, career URL, India presence, and expected access behavior.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from core import company_seeds


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = BACKEND_ROOT / "core"
DEFAULT_OUTPUT = Path(__file__).parent / "company_benchmark.jsonl"


def _name_from_slug(slug: str) -> str:
    words = re.sub(r"[-_]+", " ", slug).strip().split()
    return " ".join(word[:1].upper() + word[1:] for word in words) or slug


def _careers_url(provider: str, slug: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    if provider == "greenhouse":
        return f"https://boards.greenhouse.io/{slug}"
    if provider == "lever":
        return f"https://jobs.lever.co/{slug}"
    if provider == "ashby":
        return f"https://jobs.ashbyhq.com/{slug}"
    if provider == "workable":
        return f"https://apply.workable.com/{slug}/"
    if provider == "smartrecruiters":
        return f"https://jobs.smartrecruiters.com/{slug}"
    if provider == "personio":
        return f"https://{slug}.jobs.personio.com/"
    if provider == "teamtailor":
        return f"https://{slug}.teamtailor.com/jobs"
    if provider == "recruitee":
        return f"https://{slug}.recruitee.com/"
    if provider == "breezy":
        return f"https://{slug}.breezy.hr/"
    if provider == "bamboohr":
        return f"https://{slug}.bamboohr.com/careers"
    if provider == "workday":
        tenant = extra.get("tenant") or slug
        host = extra.get("host") or "wd5"
        site = extra.get("site") or "External"
        return f"https://{tenant}.{host}.myworkdayjobs.com/{site}"
    return f"https://{slug}.com/careers"


def _scan_target(provider: str, slug: str, extra: dict[str, Any] | None = None) -> str:
    extra = extra or {}
    if provider == "workday":
        tenant = str(extra.get("tenant") or slug)
        host = str(extra.get("host") or "wd5")
        site = str(extra.get("site") or "External")
        return f"ats:workday:{tenant}:{host}:{site}:engineer"
    return f"ats:{provider}:{slug}"


def _load_inventory(name: str) -> list[dict[str, Any]]:
    path = CORE_DIR / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def collect_company_benchmark(limit: int = 120) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for provider, slug in company_seeds._TECH_SEEDS:
        candidates.append((provider, slug, "tech_seed", "core.company_seeds", {}))
    # Insert enterprise/GCC-heavy Workday boards before the much larger AI-board
    # inventory so a bounded benchmark cannot fill entirely with startup ATSs.
    for board in company_seeds._load_workday_boards():
        tenant = str(board.get("tenant") or "")
        if tenant:
            candidates.append(("workday", tenant, "giant_gcc_mnc", "core.workday_seeds", board))
    for item in _load_inventory("ai_boards.json"):
        provider, slug = str(item.get("provider") or ""), str(item.get("slug") or "")
        if provider and slug:
            candidates.append((provider, slug, "ai_data_devtools", "core.ai_boards", item))
    for item in _load_inventory("new_boards.json"):
        provider, slug = str(item.get("provider") or ""), str(item.get("slug") or "")
        if provider and slug:
            candidates.append((provider, slug, "unclassified", "core.new_boards", item))

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for provider, slug, proposed_cohort, inventory_source, extra in candidates:
        key = (provider.lower(), slug.lower())
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "schema_version": 1,
                "company_id": f"{provider}:{slug}".lower(),
                "name": _name_from_slug(slug),
                "proposed_cohort": proposed_cohort,
                "provider": provider.lower(),
                "tenant_or_slug": slug,
                "careers_url": _careers_url(provider.lower(), slug, extra),
                "scan_target": _scan_target(provider.lower(), slug, extra),
                "india_presence": "unknown",
                "known_remote_scope": "unknown",
                "expected_access": "public_career_site",
                "priority": 1 if proposed_cohort in {"tech_seed", "ai_data_devtools"} else 2,
                "inventory_source": inventory_source,
                "inventory_job_count": int(extra.get("jobs") or extra.get("total") or 0),
                "review_status": "needs_review",
                "last_verified_at": None,
                "notes": "Generated crawl candidate; human verification required before benchmark scoring.",
            }
        )
        if len(records) >= max(1, limit):
            break
    return records


def validate_company_benchmark(records: list[dict[str, Any]], *, minimum: int = 100) -> list[str]:
    errors: list[str] = []
    if len(records) < minimum:
        errors.append(f"benchmark has {len(records)} entries; minimum is {minimum}")
    ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        label = f"entry {index}"
        for key in (
            "company_id",
            "name",
            "provider",
            "tenant_or_slug",
            "careers_url",
            "scan_target",
            "review_status",
        ):
            if not str(record.get(key) or "").strip():
                errors.append(f"{label}: missing {key}")
        company_id = str(record.get("company_id") or "")
        if company_id in ids:
            errors.append(f"{label}: duplicate company_id {company_id}")
        ids.add(company_id)
        if not str(record.get("careers_url") or "").startswith("https://"):
            errors.append(f"{label}: careers_url must be HTTPS")
        if record.get("review_status") not in {"needs_review", "single_review", "double_review"}:
            errors.append(f"{label}: invalid review_status")
    return errors


def write_company_benchmark(path: Path = DEFAULT_OUTPUT, *, limit: int = 120) -> list[dict[str, Any]]:
    records = collect_company_benchmark(limit=limit)
    errors = validate_company_benchmark(records)
    if errors:
        raise ValueError("Invalid generated benchmark:\n" + "\n".join(errors))
    payload = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records) + "\n"
    path.write_text(payload, encoding="utf-8")
    return records


def load_company_benchmark(path: Path = DEFAULT_OUTPUT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_no}: entry must be an object")
        records.append(value)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the generated JSONL benchmark")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = write_company_benchmark(args.output, limit=args.limit) if args.write else collect_company_benchmark(args.limit)
    errors = validate_company_benchmark(records)
    print(f"Company benchmark candidates: {len(records)}")
    print(f"Review status: {sum(r['review_status'] == 'needs_review' for r in records)} need human review")
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Schema validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
