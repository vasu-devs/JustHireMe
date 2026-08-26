"""Compare versioned candidate decisions across two opportunity-index snapshots."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def _load(path: Path, *, candidate_id: str, rule_version: str) -> dict[str, dict]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT d.opportunity_id, d.payload_json, c.employer_name, c.title,
                   c.location_text, c.canonical_apply_url
            FROM candidate_opportunity_decisions AS d
            JOIN canonical_opportunities AS c
              ON c.opportunity_id = d.opportunity_id
            WHERE d.candidate_id = ? AND d.rule_version = ?
            """,
            (candidate_id, rule_version),
        ).fetchall()
    finally:
        connection.close()
    result: dict[str, dict] = {}
    for row in rows:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError(f"decision payload is not an object: {row['opportunity_id']}")
        result[row["opportunity_id"]] = {
            "payload": payload,
            "employer": row["employer_name"],
            "title": row["title"],
            "location": row["location_text"],
            "url": row["canonical_apply_url"],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_db", type=Path)
    parser.add_argument("new_db", type=Path)
    parser.add_argument("--candidate-id", default="phase0-representative-cse")
    parser.add_argument("--old-rule", required=True)
    parser.add_argument("--new-rule", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    old = _load(args.old_db.resolve(), candidate_id=args.candidate_id, rule_version=args.old_rule)
    new = _load(args.new_db.resolve(), candidate_id=args.candidate_id, rule_version=args.new_rule)
    shared = sorted(old.keys() & new.keys())
    field_counts: Counter[str] = Counter()
    changes: list[dict] = []
    ignored = {"rule_version"}
    for opportunity_id in shared:
        old_payload = old[opportunity_id]["payload"]
        new_payload = new[opportunity_id]["payload"]
        field_changes = {}
        for field in sorted((old_payload.keys() | new_payload.keys()) - ignored):
            before = old_payload.get(field)
            after = new_payload.get(field)
            if before != after:
                field_counts[field] += 1
                field_changes[field] = {"from": before, "to": after}
        if field_changes:
            identity = {key: old[opportunity_id][key] for key in ("employer", "title", "location", "url")}
            changes.append({
                "opportunity_id": opportunity_id,
                **identity,
                "changes": field_changes,
            })

    report = {
        "candidate_id": args.candidate_id,
        "old_rule": args.old_rule,
        "new_rule": args.new_rule,
        "old_opportunities": len(old),
        "new_opportunities": len(new),
        "paired_opportunities": len(shared),
        "missing_from_old": sorted(new.keys() - old.keys()),
        "missing_from_new": sorted(old.keys() - new.keys()),
        "changed_opportunities": len(changes),
        "field_change_counts": dict(sorted(field_counts.items())),
        "changes": changes,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        destination = args.report.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
