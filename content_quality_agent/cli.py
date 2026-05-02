"""CLI wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_quality_agent.config import load_runtime_config
from content_quality_agent.fix_workflow import apply_approved_spelling_fixes, generate_spelling_lesson_fix_suggestions
from content_quality_agent.runner import run_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline content-quality audit agent for Kiarolabs.")
    parser.add_argument(
        "--mode",
        choices=("words", "spelling", "all", "generate-fixes", "apply-approved-fixes"),
        required=True,
    )
    parser.add_argument("--lesson-id", type=int)
    parser.add_argument("--pattern-id", type=int)
    parser.add_argument("--since")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reports-dir")
    parser.add_argument("--source")
    parser.add_argument("--file")
    parser.add_argument("--allow-partial", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_runtime_config(reports_dir_override=args.reports_dir)

    try:
        if args.mode in {"words", "spelling", "all"}:
            payload = run_audit(
                config=config,
                mode=args.mode,
                lesson_id=args.lesson_id,
                pattern_id=args.pattern_id,
                since=args.since,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        elif args.mode == "generate-fixes":
            if not args.source:
                raise RuntimeError("--source is required for --mode generate-fixes")
            payload = generate_spelling_lesson_fix_suggestions(
                config=config,
                source_path=Path(args.source),
            )
        else:
            if not args.file:
                raise RuntimeError("--file is required for --mode apply-approved-fixes")
            payload = apply_approved_spelling_fixes(
                config=config,
                approved_path=Path(args.file),
                dry_run=args.dry_run,
                allow_partial=args.allow_partial,
            )
    except Exception as exc:  # pragma: no cover - thin CLI fallback
        print(f"Audit failed safely: {exc}")
        return 1

    if args.mode in {"words", "spelling", "all"}:
        print(json.dumps(
            {
                "run_id": payload["run_id"],
                "mode": payload["mode"],
                "dry_run": payload["dry_run"],
                "findings": len(payload["findings"]),
                "reports_dir": payload["reports_dir"],
            },
            indent=2,
        ))
    else:
        print(json.dumps(payload, indent=2))
    return 0
