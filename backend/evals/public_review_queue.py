"""Collect bounded public ATS observations for independent Phase-0 review.

The output is deliberately *not* the gold corpus. Automated tags are proposed
triage hints, descriptions are reduced to short evidence excerpts plus hashes,
and every row remains ``unreviewed`` until the rubric's human review completes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discovery.normalizer import clean_text
from discovery.sources.ats import scrape_target
from evals.company_benchmark import DEFAULT_OUTPUT as COMPANY_BENCHMARK_PATH
from evals.company_benchmark import load_company_benchmark
from evals.opportunity_contracts import TARGET_CATEGORY_COUNTS


OUTPUT_DIR = Path(__file__).parent / "output"
DEFAULT_QUEUE_PATH = OUTPUT_DIR / "public_opportunity_review_queue.jsonl"
DEFAULT_REPORT_PATH = OUTPUT_DIR / "public_opportunity_review_report.json"

_EARLY_RE = re.compile(
    r"\b(intern(?:ship)?|co-?op|new\s*grad(?:uate)?|graduate|fresher|entry[ -]?level|junior|"
    r"associate\s+(?:software|data|cloud|security|qa|technical|systems?)|"
    r"software\s+engineer\s+(?:i|1)|sde\s*(?:i|1)|engineer\s+(?:i|1))\b",
    re.I,
)
_INTERN_RE = re.compile(r"\b(intern(?:ship)?|co-?op)\b", re.I)
_SENIOR_RE = re.compile(r"\b(senior|staff|principal|lead|manager|director|architect|[5-9]\+?\s*years)\b", re.I)
_TECH_RE = re.compile(
    r"\b(software|developer|engineer|engineering|frontend|backend|full[ -]?stack|mobile|android|ios|"
    r"machine learning|artificial intelligence|\bai\b|\bml\b|data|cloud|devops|platform|infrastructure|"
    r"site reliability|\bsre\b|security|cyber|qa automation|sdet|firmware|embedded|systems?|compiler|database)\b",
    re.I,
)
_NON_TECH_RE = re.compile(
    r"\b(marketing|sales|recruit(?:er|ing)|human resources|\bhr\b|content|finance|legal|operations|"
    r"customer success|business development|graphic design|social media)\b",
    re.I,
)
_REMOTE_RE = re.compile(r"\b(remote|work from home|distributed)\b", re.I)
_INDIA_RE = re.compile(
    r"\b(india|bengaluru|bangalore|hyderabad|pune|gurugram|gurgaon|noida|delhi|chennai|mumbai|"
    r"ahmedabad|kochi|kolkata|jaipur|coimbatore|mohali|chandigarh)\b",
    re.I,
)
_WORLDWIDE_RE = re.compile(r"\b(worldwide|anywhere|global remote|work from anywhere)\b", re.I)
_RESTRICTED_REMOTE_RE = re.compile(
    r"\b(us|u\.s\.|united states|canada|uk|united kingdom|eu|european union)[ -]?(?:only|based)|"
    r"(?:only|must reside|residents? of|located in).{0,30}\b(us|united states|canada|uk|eu)\b",
    re.I,
)

_CATEGORY_ORDER = (
    "india_internship",
    "india_early_career",
    "remote_india_eligible",
    "remote_india_ineligible",
    "closed_or_ambiguous",
    "non_technical",
    "seniority_trap",
)


def _proposed_category(lead: dict[str, Any]) -> tuple[str, list[str]]:
    title = clean_text(str(lead.get("title") or ""))
    location = clean_text(str(lead.get("location") or ""))
    description = clean_text(str(lead.get("description") or ""))
    text = f"{title}\n{location}\n{description}"
    tags: list[str] = []

    is_intern = bool(_INTERN_RE.search(title))
    is_early = bool(_EARLY_RE.search(title))
    is_senior = bool(_SENIOR_RE.search(title))
    is_tech = bool(_TECH_RE.search(title)) and not bool(_NON_TECH_RE.search(title))
    is_remote = bool(_REMOTE_RE.search(text))
    # India on-site/hybrid eligibility must come from the source's location
    # field. Descriptions often mention global offices or equal-opportunity
    # regions that are unrelated to the vacancy's actual workplace.
    india = bool(_INDIA_RE.search(location))
    worldwide = bool(_WORLDWIDE_RE.search(text))
    restricted_remote = bool(_RESTRICTED_REMOTE_RE.search(text))

    if is_intern:
        tags.append("intern_title")
    if is_early:
        tags.append("early_career_title")
    if is_senior:
        tags.append("senior_title")
    tags.append("technical_title" if is_tech else "technical_uncertain")
    if is_remote:
        tags.append("remote_signal")
    if india:
        tags.append("india_signal")
    if worldwide:
        tags.append("worldwide_signal")
    if restricted_remote:
        tags.append("restricted_remote_signal")

    if is_senior:
        return "seniority_trap", tags
    # The queue is for early-career market evaluation. A generic current
    # engineering vacancy is neither a positive example nor a useful negative;
    # retaining those rows lets large boards drown the signal we need to review.
    if not (is_intern or is_early):
        return "unclassified", tags
    if not is_tech and (is_intern or is_early):
        return "non_technical", tags
    if is_remote and restricted_remote and not india:
        return "remote_india_ineligible", tags
    if is_remote and (india or worldwide):
        return "remote_india_eligible", tags
    if is_remote:
        return "closed_or_ambiguous", tags
    if is_intern and india:
        return "india_internship", tags
    if is_early and india:
        return "india_early_career", tags
    if is_intern:
        return "closed_or_ambiguous", tags
    return "unclassified", tags


def select_diverse_boards(records: list[dict[str, Any]], max_boards: int) -> list[dict[str, Any]]:
    """Round-robin providers so a bounded run is not all Greenhouse/Ashby."""
    grouped: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for record in records:
        grouped[str(record.get("provider") or "unknown")].append(record)
    providers = deque(sorted(grouped, key=lambda provider: (provider == "unknown", provider)))
    selected: list[dict[str, Any]] = []
    while providers and len(selected) < max(1, max_boards):
        provider = providers.popleft()
        if grouped[provider]:
            selected.append(grouped[provider].popleft())
        if grouped[provider]:
            providers.append(provider)
    return selected


def select_diverse_entries(
    entries: list[dict[str, Any]],
    max_records: int,
    *,
    max_per_company: int = 20,
    category_limits: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Round-robin categories and companies instead of taking board order."""
    limits = category_limits or TARGET_CATEGORY_COUNTS
    grouped: dict[str, dict[str, deque[dict[str, Any]]]] = defaultdict(lambda: defaultdict(deque))
    for entry in entries:
        category = str(entry.get("proposed_category") or "unclassified")
        company_id = str(entry.get("company_benchmark_id") or "unknown")
        if category != "unclassified":
            grouped[category][company_id].append(entry)

    categories = deque(category for category in _CATEGORY_ORDER if grouped.get(category))
    company_queues = {
        category: deque(sorted(companies)) for category, companies in grouped.items() if companies
    }
    company_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    selected: list[dict[str, Any]] = []

    while categories and len(selected) < max(1, max_records):
        category = categories.popleft()
        if category_counts[category] >= limits.get(category, max_records):
            continue
        companies = company_queues[category]
        selected_entry: dict[str, Any] | None = None
        attempts = len(companies)
        for _ in range(attempts):
            company_id = companies.popleft()
            company_entries = grouped[category][company_id]
            if company_counts[company_id] < max(1, max_per_company) and company_entries:
                selected_entry = company_entries.popleft()
                company_counts[company_id] += 1
            if company_entries and company_counts[company_id] < max(1, max_per_company):
                companies.append(company_id)
            if selected_entry is not None:
                break

        if selected_entry is not None:
            selected.append(selected_entry)
            category_counts[category] += 1
        if companies and category_counts[category] < limits.get(category, max_records):
            categories.append(category)

    return selected


def make_review_entry(
    lead: dict[str, Any],
    company_record: dict[str, Any],
    *,
    observed_at: str,
    excerpt_limit: int = 600,
) -> dict[str, Any]:
    description = clean_text(str(lead.get("description") or ""))
    title = clean_text(str(lead.get("title") or ""))
    company = clean_text(str(lead.get("company") or company_record.get("name") or ""))
    url = str(lead.get("url") or "").strip()
    proposed_category, proposed_tags = _proposed_category(lead)
    digest = hashlib.sha256(description.encode("utf-8")).hexdigest()
    source_meta = lead.get("source_meta") if isinstance(lead.get("source_meta"), dict) else {}
    return {
        "schema_version": 1,
        "review_id": hashlib.sha256(f"{company_record.get('company_id')}|{url}".encode()).hexdigest()[:20],
        "review_status": "unreviewed",
        "automated_labels_are_proposed": True,
        "proposed_category": proposed_category,
        "proposed_tags": proposed_tags,
        "company_benchmark_id": company_record.get("company_id"),
        "posting": {
            "title": title,
            "company": company,
            "url": url,
            "source": str(lead.get("platform") or company_record.get("provider") or "unknown"),
            "location": clean_text(str(lead.get("location") or "")),
            "posted_at": str(lead.get("posted_date") or ""),
            "observed_at": observed_at,
            "description_excerpt": description[:excerpt_limit],
            "description_sha256": digest,
            "source_record_id": str(source_meta.get("id") or source_meta.get("job_id") or ""),
        },
        "provenance": {
            "scan_target": company_record.get("scan_target"),
            "careers_url": company_record.get("careers_url"),
            "inventory_source": company_record.get("inventory_source"),
            "captured_at": observed_at,
        },
        "human_review": {
            "reviewers": [],
            "final_category": None,
            "expected_decision": None,
            "evidence": [],
            "notes": "",
        },
    }


@dataclass(frozen=True)
class CollectionResult:
    entries: list[dict[str, Any]]
    errors: list[str]
    source_counts: dict[str, int]
    boards_requested: int
    boards_attempted: int
    boards_succeeded: int
    candidate_pool_size: int


async def collect_review_queue(
    company_records: list[dict[str, Any]],
    *,
    scraper: Callable[[str], Awaitable[list[dict]]] = scrape_target,
    max_records: int = 250,
    max_per_board: int = 30,
    max_per_company: int = 20,
    max_concurrency: int = 6,
) -> CollectionResult:
    observed_at = datetime.now(timezone.utc).isoformat()
    candidate_pool: list[dict[str, Any]] = []
    errors: list[str] = []
    source_counts: dict[str, int] = {}
    seen_urls: set[str] = set()
    scan_inputs: list[tuple[dict[str, Any], str]] = []
    for company_record in company_records:
        target = str(company_record.get("scan_target") or "").strip()
        if not target:
            errors.append(f"{company_record.get('company_id')}: missing scan_target")
            continue
        scan_inputs.append((company_record, target))

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def scan_one(
        company_record: dict[str, Any], target: str
    ) -> tuple[dict[str, Any], list[dict], str | None]:
        try:
            async with semaphore:
                leads = await scraper(target)
        except Exception as exc:  # source failures are data in the Phase-0 report
            return company_record, [], f"{company_record.get('company_id')}: {type(exc).__name__}: {exc}"
        return company_record, leads, None

    scan_results = await asyncio.gather(
        *(scan_one(company_record, target) for company_record, target in scan_inputs)
    )
    boards_succeeded = 0
    for company_record, leads, error in scan_results:
        if error:
            errors.append(error)
            continue
        boards_succeeded += 1
        provider = str(company_record.get("provider") or "unknown")
        source_counts[provider] = source_counts.get(provider, 0) + len(leads)
        board_candidates = 0
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            url = str(lead.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            # Keep early-career positives and deliberate negatives such as
            # seniority traps. Generic experienced vacancies are excluded.
            category, _tags = _proposed_category(lead)
            if category == "unclassified":
                continue
            seen_urls.add(url)
            candidate_pool.append(make_review_entry(lead, company_record, observed_at=observed_at))
            board_candidates += 1
            if board_candidates >= max(1, max_per_board):
                break

    entries = select_diverse_entries(
        candidate_pool,
        max_records,
        max_per_company=max_per_company,
    )
    return CollectionResult(
        entries=entries,
        errors=errors,
        source_counts=source_counts,
        boards_requested=len(company_records),
        boards_attempted=len(scan_inputs),
        boards_succeeded=boards_succeeded,
        candidate_pool_size=len(candidate_pool),
    )


def write_collection(
    result: CollectionResult,
    *,
    queue_path: Path = DEFAULT_QUEUE_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in result.entries)
    queue_path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    category_counts: dict[str, int] = {}
    for entry in result.entries:
        category = str(entry.get("proposed_category") or "unclassified")
        category_counts[category] = category_counts.get(category, 0) + 1
    companies = {str(entry.get("company_benchmark_id") or "unknown") for entry in result.entries}
    providers = {str(entry.get("posting", {}).get("source") or "unknown") for entry in result.entries}
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "boards_requested": result.boards_requested,
        "boards_attempted": result.boards_attempted,
        "boards_succeeded": result.boards_succeeded,
        "candidate_pool_size": result.candidate_pool_size,
        "records_collected": len(result.entries),
        "unique_companies_in_queue": len(companies),
        "providers_in_queue": sorted(providers),
        "automated_labels_are_proposed": True,
        "reviewed_records": 0,
        "source_counts": result.source_counts,
        "proposed_category_counts": category_counts,
        "errors": result.errors,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=COMPANY_BENCHMARK_PATH)
    parser.add_argument("--max-boards", type=int, default=24)
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    records = select_diverse_boards(load_company_benchmark(args.benchmark), args.max_boards)
    result = asyncio.run(collect_review_queue(records, max_records=args.max_records))
    write_collection(result, queue_path=args.queue, report_path=args.report)
    print(f"Boards attempted: {result.boards_attempted}")
    print(f"Boards succeeded: {result.boards_succeeded}")
    print(f"Eligible candidate pool: {result.candidate_pool_size}")
    print(f"Review candidates collected: {len(result.entries)}")
    print(f"Source errors: {len(result.errors)}")
    print(f"Queue: {args.queue}")
    print(f"Report: {args.report}")
    return 0 if result.entries else 1


if __name__ == "__main__":
    raise SystemExit(main())
