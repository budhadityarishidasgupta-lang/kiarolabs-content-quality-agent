"""Audit-only CLI wiring."""

from __future__ import annotations

import argparse
import json

from content_quality_agent.config import load_runtime_config
from content_quality_agent.runner import run_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only content-quality audit agent for Kiarolabs. Reports probable errors; never changes content."
    )
    parser.add_argument(
        "--mode",
        choices=("words", "spelling", "math", "vr", "all"),
        required=True,
    )
    parser.add_argument("--lesson-id", type=int)
    parser.add_argument("--pattern-id", type=int)
    parser.add_argument("--since")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reports-dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_runtime_config(reports_dir_override=args.reports_dir)

    try:
        payload = run_audit(
            config=config,
            mode=args.mode,
            lesson_id=args.lesson_id,
            pattern_id=args.pattern_id,
            since=args.since,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # pragma: no cover
        print(f"Audit failed safely: {exc}")
        return 1

    print(json.dumps(
        {
            "run_id": payload["run_id"],
            "mode": payload["mode"],
            "dry_run": payload["dry_run"],
            "findings": len(payload["findings"]),
            "reports_dir": payload["reports_dir"],
            "content_changes_applied": 0,
            "human_review_required": True,
        },
        indent=2,
    ))
    return 0
