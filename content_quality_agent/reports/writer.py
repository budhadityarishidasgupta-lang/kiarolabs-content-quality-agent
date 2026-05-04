"""Write latest and per-run report artifacts."""

from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime, timezone

from content_quality_agent.reports.atomic_write import atomic_write_json, atomic_write_text
from content_quality_agent.reports.formatter import format_csv_rows, format_json, format_markdown
from content_quality_agent.reports.review_queue import format_review_queue_csv
from content_quality_agent.reports.scoring import calculate_scores


def _severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = finding.get("severity", "low")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _app_counts(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        app = finding.get("app", "unknown")
        counts[app] = counts.get(app, 0) + 1
    return counts


def _coverage_warning(run_payload: dict) -> str:
    coverage = run_payload["coverage"]
    warnings: list[str] = []
    if run_payload.get("dry_run"):
        warnings.append("Dry-run only: no full content scan was performed.")
    if coverage.get("overall_coverage_pct", 0.0) < 100.0:
        warnings.append(
            f"Overall coverage is partial at {coverage.get('overall_coverage_pct', 0.0):.2f}%."
        )
    if coverage.get("checks_skipped"):
        warnings.append(
            f"Skipped checks detected: {', '.join(coverage['checks_skipped'])}."
        )
    if coverage.get("suppressed_findings", 0):
        warnings.append(f"{coverage['suppressed_findings']} findings were suppressed by allowlist.")
    if coverage.get("words_audit_partial"):
        warnings.append("Words audit is partial due to mixed content shape.")
    if coverage.get("capped_findings", 0):
        warnings.append(f"{coverage['capped_findings']} Words findings were capped.")
    if not coverage.get("llm_available", False):
        warnings.append("LLM-assisted semantic checks were unavailable.")
    if coverage.get("notes"):
        warnings.extend(str(note) for note in coverage["notes"])
    return " ".join(warnings) if warnings else "No coverage warnings."


def _recommended_actions(run_payload: dict) -> list[str]:
    findings = run_payload["findings"]
    critical_or_high = [
        finding for finding in findings if finding.get("severity") in {"critical", "high"}
    ]
    actions: list[str] = []
    if critical_or_high:
        actions.append("Review critical and high-severity findings first.")
    if any(finding.get("human_review_required") for finding in findings):
        actions.append("Queue human review for findings flagged as requiring approval.")
    coverage = run_payload["coverage"]
    if coverage.get("checks_skipped") or coverage.get("overall_coverage_pct", 0.0) < 100.0:
        actions.append("Re-run with fuller coverage before treating a clean report as complete.")
    if not actions:
        actions.append("No urgent follow-up actions were generated for this run.")
    return actions


def _format_executive_summary(run_payload: dict) -> str:
    findings = run_payload["findings"]
    severity_counts = _severity_counts(findings)
    app_counts = _app_counts(findings)
    coverage_warning = _coverage_warning(run_payload)
    actions = _recommended_actions(run_payload)
    scores = run_payload["scores"]
    top_review_items = sorted(
        findings,
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.get("severity", "low"), 4),
            -(item.get("confidence", 0.0) or 0.0),
        ),
    )[:10]

    lines = [
        "# Executive Summary",
        "",
        f"- Run ID: `{run_payload['run_id']}`",
        f"- Mode: `{run_payload['mode']}`",
        f"- Dry-run: `{run_payload['dry_run']}`",
        f"- Total findings: `{len(findings)}`",
        f"- Suppressed findings: `{run_payload['coverage'].get('suppressed_findings', 0)}`",
        f"- Capped findings: `{run_payload['coverage'].get('capped_findings', 0)}`",
        f"- Overall Content Quality Score: `{scores['overall_content_quality_score']}`",
        f"- Spelling Score: `{scores['spelling_score']}`",
        f"- Words Score: `{scores['words_score']}`",
        f"- Words schema classification: `{run_payload['coverage'].get('words_schema_classification') or 'n/a'}`",
        f"- Words schema confidence: `{run_payload['coverage'].get('words_schema_confidence', 0.0):.2f}`",
        "",
        "## Findings by severity",
        f"- Critical: `{severity_counts.get('critical', 0)}`",
        f"- High: `{severity_counts.get('high', 0)}`",
        f"- Medium: `{severity_counts.get('medium', 0)}`",
        f"- Low: `{severity_counts.get('low', 0)}`",
        "",
        "## Findings by app",
    ]
    if app_counts:
        for app, count in sorted(app_counts.items()):
            lines.append(f"- {app}: `{count}`")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Coverage notes",
        ]
    )
    if coverage := run_payload.get("coverage", {}):
        for note in coverage.get("notes", []):
            lines.append(f"- {note}")
    if not run_payload.get("coverage", {}).get("notes"):
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Coverage warning",
            f"- {coverage_warning}",
            "",
            "## Top 10 human review items",
        ]
    )
    if top_review_items:
        for item in top_review_items:
            lines.append(
                f"- `{item['severity']}` `{item['app']}` `{item['issue_type']}` on `{item['table_name']}` `{item['record_id']}` (confidence `{item.get('confidence', 0.0):.2f}`)"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            f"- Review queue: `{run_payload['review_queue_path']}`",
            "",
            "## Top recommended human actions",
        ]
    )
    lines.extend(f"- {action}" for action in actions)
    return "\n".join(lines).strip() + "\n"


def _build_latest_run_metadata(*, run_id: str, run_payload: dict, run_dir: Path) -> dict:
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": run_payload["mode"],
        "dry_run": run_payload["dry_run"],
        "source_run_dir": str(run_dir),
    }


def _build_manifest(
    *,
    run_id: str,
    run_payload: dict,
    run_dir: Path,
    reports_written: list[str],
    latest_files_updated: list[str],
) -> dict:
    scores = run_payload.get("scores", {})
    coverage = run_payload.get("coverage", {})
    return {
        "run_id": run_id,
        "mode": run_payload["mode"],
        "dry_run": run_payload["dry_run"],
        "started_at": run_payload.get("started_at"),
        "completed_at": run_payload.get("completed_at"),
        "reports_written": reports_written,
        "latest_files_updated": latest_files_updated,
        "findings_count": len(run_payload.get("findings", [])),
        "score_summary": {
            "overall_content_quality_score": scores.get("overall_content_quality_score"),
            "spelling_score": scores.get("spelling_score"),
            "words_score": scores.get("words_score"),
        },
        "coverage_summary": {
            "total_records_discovered": coverage.get("total_records_discovered"),
            "records_checked": coverage.get("records_checked"),
            "suppressed_findings": coverage.get("suppressed_findings"),
            "capped_findings": coverage.get("capped_findings"),
            "overall_coverage_pct": coverage.get("overall_coverage_pct"),
            "words_schema_classification": coverage.get("words_schema_classification"),
        },
        "source_run_dir": str(run_dir),
    }


def write_reports(*, reports_dir: Path, run_id: str, run_payload: dict, diff_payload: dict | None) -> None:
    run_dir = reports_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_payload = dict(run_payload)

    findings = run_payload["findings"]
    csv_rows = []
    for finding in findings:
        row = dict(finding)
        row["identity_key"] = "|".join(
            [finding["app"], finding["table_name"], str(finding["record_id"]), finding["issue_type"], finding["current_value"]]
        )
        csv_rows.append(row)

    scores = calculate_scores(run_payload)
    run_payload["scores"] = scores
    run_payload["review_queue_path"] = str(reports_dir / "review-queue-latest.csv")
    markdown = format_markdown(run_payload, diff_payload)
    json_payload = format_json(run_payload)
    csv_payload = format_csv_rows(findings)
    review_queue_payload = format_review_queue_csv(findings)
    coverage_payload = json.dumps(run_payload["coverage"], indent=2)
    executive_summary = _format_executive_summary(run_payload)
    effective_diff = diff_payload or {
        "new_findings": [],
        "persisting_findings": [],
        "resolved_findings": [],
    }
    diff_md = [
        "# Audit Diff",
        "",
        f"- New findings: {len(effective_diff['new_findings'])}",
        f"- Persisting findings: {len(effective_diff['persisting_findings'])}",
        f"- Resolved findings: {len(effective_diff['resolved_findings'])}",
        "",
    ]
    run_specific_files = {
        "content-quality-report.md": markdown,
        "content-quality-report.json": json_payload,
        "content-quality-errors.csv": csv_payload,
        "coverage.json": coverage_payload,
        "review-queue.csv": review_queue_payload,
    }
    for name, content in run_specific_files.items():
        atomic_write_text(run_dir / name, content)

    latest_files = {
        "content-quality-latest.md": markdown,
        "content-quality-latest.json": json_payload,
        "content-quality-errors.csv": csv_payload,
        "content-quality-coverage-latest.json": coverage_payload,
        "review-queue-latest.csv": review_queue_payload,
        "executive-summary-latest.md": executive_summary,
        "audit-diff-latest.json": json.dumps(effective_diff, indent=2),
        "audit-diff-latest.md": "\n".join(diff_md),
    }
    latest_run_metadata = _build_latest_run_metadata(run_id=run_id, run_payload=run_payload, run_dir=run_dir)
    manifest = _build_manifest(
        run_id=run_id,
        run_payload=run_payload,
        run_dir=run_dir,
        reports_written=sorted(run_specific_files.keys()),
        latest_files_updated=sorted([*latest_files.keys(), "latest-run.json"]),
    )
    atomic_write_json(run_dir / "manifest.json", manifest)

    for name, content in latest_files.items():
        atomic_write_text(reports_dir / name, content)
    atomic_write_json(reports_dir / "latest-run.json", latest_run_metadata)
