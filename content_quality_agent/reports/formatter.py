"""Format audit runs into Markdown, JSON, and CSV-friendly payloads."""

from __future__ import annotations

import csv
import io
import json


def format_json(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def format_csv_rows(findings: list[dict]) -> str:
    fieldnames = [
        "run_id",
        "app",
        "severity",
        "confidence",
        "issue_type",
        "table_name",
        "record_id",
        "lesson_id",
        "pattern_id",
        "word",
        "headword",
        "current_value",
        "suggested_fix",
        "explanation",
        "human_review_required",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for finding in findings:
        writer.writerow({field: finding.get(field) for field in fieldnames})
    return buffer.getvalue()


def format_markdown(run_payload: dict, diff_payload: dict | None = None) -> str:
    coverage = run_payload["coverage"]
    findings = run_payload["findings"]
    scores = run_payload.get("scores", {})
    review_queue_path = run_payload.get("review_queue_path", "reports/review-queue-latest.csv")
    by_severity: dict[str, list[dict]] = {"critical": [], "high": [], "medium": [], "low": []}
    by_app: dict[str, int] = {}
    for finding in findings:
        by_severity.setdefault(finding["severity"], []).append(finding)
        app = finding.get("app", "unknown")
        by_app[app] = by_app.get(app, 0) + 1

    top_review_items = sorted(
        findings,
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.get("severity", "low"), 4),
            -(item.get("confidence", 0.0) or 0.0),
        ),
    )[:10]

    coverage_warnings = []
    if run_payload.get("dry_run"):
        coverage_warnings.append("Dry-run only: no full content scan was performed.")
    if coverage["overall_coverage_pct"] < 100.0:
        coverage_warnings.append(f"Overall coverage is partial at {coverage['overall_coverage_pct']:.2f}%.")
    if coverage["checks_skipped"]:
        coverage_warnings.append(f"Skipped checks: {', '.join(coverage['checks_skipped'])}.")
    if coverage.get("suppressed_findings", 0):
        coverage_warnings.append(f"Suppressed findings: {coverage['suppressed_findings']}.")
    if coverage.get("words_audit_partial"):
        coverage_warnings.append("Words audit is partial because the content shape is mixed or unclear.")
    if coverage.get("capped_findings", 0):
        coverage_warnings.append(f"Capped Words findings: {coverage['capped_findings']}.")

    lines = [
        "# Content Quality Audit Report",
        "",
        "## Executive summary",
        f"- Mode: `{run_payload['mode']}`",
        f"- Dry-run: `{run_payload['dry_run']}`",
        f"- Findings: `{len(findings)}`",
        f"- Suppressed findings: `{coverage.get('suppressed_findings', 0)}`",
        f"- Capped findings: `{coverage.get('capped_findings', 0)}`",
        f"- Guardrail status: `{run_payload['guardrail_status']}`",
        "",
        "## Scores",
        f"- Overall Content Quality Score: `{scores.get('overall_content_quality_score', 0)}`",
        f"- Spelling Score: `{scores.get('spelling_score', 0)}`",
        f"- Words Score: `{scores.get('words_score', 0)}`",
        f"- Severity Penalty: `{scores.get('severity_penalty', 0)}`",
        f"- Coverage Penalty: `{scores.get('coverage_penalty', 0)}`",
        f"- Confidence-adjusted Risk Score: `{scores.get('confidence_adjusted_risk_score', 0)}`",
        "",
        "## Run metadata",
        f"- Run ID: `{run_payload['run_id']}`",
        f"- Started at: `{run_payload['started_at']}`",
        f"- Reports dir: `{run_payload['reports_dir']}`",
        "",
        "## Coverage summary",
        f"- Total records discovered: `{coverage['total_records_discovered']}`",
        f"- Records checked: `{coverage['records_checked']}`",
        f"- Records skipped: `{coverage['records_skipped']}`",
        f"- Suppressed findings: `{coverage.get('suppressed_findings', 0)}`",
        f"- Capped findings: `{coverage.get('capped_findings', 0)}`",
        f"- LLM available: `{coverage['llm_available']}`",
        f"- Deterministic coverage: `{coverage['deterministic_coverage_pct']:.2f}%`",
        f"- Semantic coverage: `{coverage['semantic_coverage_pct']:.2f}%`",
        f"- Overall coverage: `{coverage['overall_coverage_pct']:.2f}%`",
        f"- Words schema classification: `{coverage.get('words_schema_classification') or 'n/a'}`",
        f"- Words schema confidence: `{coverage.get('words_schema_confidence', 0.0):.2f}`",
        "",
        "## Findings by app",
    ]
    if by_app:
        for app, count in sorted(by_app.items()):
            lines.append(f"- {app}: `{count}`")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Coverage notes",
            *([f"- {note}" for note in coverage.get("notes", [])] if coverage.get("notes") else ["- None"]),
            "",
            "## Coverage warning",
            *( [f"- {warning}" for warning in coverage_warnings] if coverage_warnings else ["- No coverage warnings."] ),
            "",
        ]
    )

    for severity in ("critical", "high", "medium", "low"):
        lines.append(f"## {severity.title()} findings")
        items = by_severity.get(severity, [])
        if not items:
            lines.append("- None")
        else:
            for item in items:
                lines.append(
                    f"- `{item['app']}` `{item['table_name']}` `{item['record_id']}` `{item['issue_type']}`: {item['explanation']}"
                )
        lines.append("")

    lines.extend(
        [
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
            f"- Review queue: `{review_queue_path}`",
            "",
        ]
    )

    lines.extend(
        [
            "## Skipped checks",
            *(
                [f"- `{name}`" for name in coverage["checks_skipped"]]
                if coverage["checks_skipped"]
                else ["- None"]
            ),
            "",
            "## New vs persisting vs resolved findings",
        ]
    )
    if diff_payload:
        lines.extend(
            [
                f"- New findings: `{len(diff_payload['new_findings'])}`",
                f"- Persisting findings: `{len(diff_payload['persisting_findings'])}`",
                f"- Resolved findings: `{len(diff_payload['resolved_findings'])}`",
            ]
        )
    else:
        lines.append("- No previous run to diff against.")
    lines.extend(
        [
            "",
            "## Recommended next actions",
            "- Review critical and high-severity findings first.",
            "- Confirm skipped semantic checks before treating a clean report as complete.",
            "",
            "## Guardrail status",
            f"- `{run_payload['guardrail_status']}`",
        ]
    )
    return "\n".join(lines).strip() + "\n"
