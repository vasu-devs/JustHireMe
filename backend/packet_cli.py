from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from application_packets import PacketCommandError, generate_application_packet, render_packet_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or retrieve a safe JustHireMe application packet for a selected job lead.",
    )
    parser.add_argument("job_id", nargs="?", help="Existing lead/job id. A URL may also be passed here.")
    parser.add_argument("--job-url", help="Existing lead URL to look up in the local lead store.")
    parser.add_argument("--high-score", action="store_true", help="Select the highest-score stored job lead.")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum score when selecting --high-score.")
    parser.add_argument("--output-root", type=Path, help="Directory for recoverable packet artifacts.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Safe mode: write artifacts only; do not mutate leads or submit applications. Default: on.")
    parser.add_argument("--force", action="store_true", help="Regenerate Markdown artifacts instead of reusing existing resume/cover assets.")
    parser.add_argument("--submit", action="store_true", help="Unsupported guardrail flag; always fails because this CLI never submits applications.")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="json", help="Stdout format. JSON is always recoverable in packet_index.json.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = generate_application_packet(
            args.job_id,
            job_url=args.job_url,
            output_root=args.output_root,
            dry_run=args.dry_run,
            submit=args.submit,
            high_score=args.high_score,
            min_score=args.min_score,
            force=args.force,
        )
    except PacketCommandError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False))
    elif args.format == "markdown":
        print(render_packet_summary(packet), end="")
    else:
        print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False))
        print("\n---\n")
        print(render_packet_summary(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
