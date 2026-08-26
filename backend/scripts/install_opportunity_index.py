from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.paths import adopt_tauri_app_data_dir_if_unset

adopt_tauri_app_data_dir_if_unset()

from data.sqlite.connection import DEFAULT_DB_PATH, close_all  # noqa: E402
from data.sqlite.opportunity_index import inspect_public_index, sync_public_index  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely merge a verified public opportunity index into JustHireMe."
    )
    parser.add_argument("--source", required=True, help="Verified SQLite opportunity-index artifact")
    parser.add_argument(
        "--destination",
        default=DEFAULT_DB_PATH,
        help="Installed JustHireMe crm.db (auto-detects an existing Tauri data root)",
    )
    parser.add_argument("--backup", help="Required backup output path unless --inspect-only is used")
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Validate and report the source without changing the destination",
    )
    parser.add_argument("--report", help="Optional JSON report output path")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.inspect_only:
        result = inspect_public_index(args.source, include_sha256=True)
    else:
        if not args.backup:
            raise SystemExit("--backup is required for an installation")
        close_all()
        result = sync_public_index(
            args.source,
            destination_path=args.destination,
            backup_path=args.backup,
        )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
