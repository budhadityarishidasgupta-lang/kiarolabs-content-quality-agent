"""Top-level audit runner."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import secrets

from content_quality_agent.auditors.spelling_auditor import audit_spelling
from content_quality_agent.auditors.words_auditor import audit_words
from content_quality_agent.db.connection import connect
from content_quality_agent.db.repository import GuardedRepository, RepositoryContext
from content_quality_agent.db.schema_discovery import discover_tables
from content_quality_agent.models.audit_run import AuditRun
from content_quality_agent.models.finding import Finding
from content_quality_agent.guardrails import GuardrailEnforcer
from content_quality_agent.reports.diff import build_diff
from content_quality_agent.reports.writer import write_reports


def generate_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"{current.strftime('audit-%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}"


def _previous_findings(reports_dir: Path) -> list[dict] | None:
    latest = reports_dir / "content-quality-latest.json"
    if not latest.exists():
        return None
    payload = json.loads(latest.read_text(encoding="utf-8"))
    findings = payload.get("findings", [])
    for finding in findings:
        finding["identity_key"] = "|".join(
            [finding["app"], finding["table_name"], str(finding["record_id"]), finding["issue_type"], finding["current_value"]]
        )
    return findings


def run_audit(*, config, mode: str, lesson_id: int | None = None, pattern_id: int | None = None, since: str | None = None, limit: int | None = None, dry_run: bool = False):
    if not config.db_url:
        raise RuntimeError("CONTENT_AUDIT_DB_URL is required for audit execution.")

    run = AuditRun(
        run_id=generate_run_id(),
        mode=mode,
        dry_run=dry_run,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        reports_dir=str(config.reports_dir),
        llm_available=bool(config.openai_api_key),
    )

    config.reports_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(config.db_url)
    try:
        discovery = discover_tables(
            conn,
            config.table_allowlist,
            config.reports_dir / "schema-discovery-latest.json",
        )
        run.schema_summary = discovery.to_dict()
        run.coverage.llm_available = bool(config.openai_api_key)

        if dry_run:
            run.coverage.checks_skipped.extend(["full_content_scan"])
            run.coverage.skip_reasons.append(
                f"Dry-run only validates connectivity, allowlists, and requested scope for mode={mode}, lesson_id={lesson_id}, pattern_id={pattern_id}, since={since}, limit={limit}."
            )
            run.completed_at = datetime.now(timezone.utc).isoformat()
            payload = _serialize_run(run)
            diff = build_diff(payload["findings"], _previous_findings(config.reports_dir))
            write_reports(reports_dir=config.reports_dir, run_id=run.run_id, run_payload=payload, diff_payload=diff)
            return payload

        guardrails = GuardrailEnforcer()
        findings: list[Finding] = []

        if mode in {"spelling", "all"}:
            spelling_repo = GuardedRepository(
                conn,
                guardrails,
                RepositoryContext("spelling", frozenset(discovery.spelling_tables)),
            )
            findings.extend(
                audit_spelling(
                    run_id=run.run_id,
                    repository=spelling_repo,
                    coverage=run.coverage,
                    limit=limit,
                )
            )

        if mode in {"words", "all"}:
            if not discovery.words_discovery_confident:
                findings.append(
                    Finding(
                        run_id=run.run_id,
                        app="words",
                        table_name="schema.discovery",
                        record_id="words",
                        lesson_id=None,
                        pattern_id=None,
                        word=None,
                        headword=None,
                        current_value="words_schema_unknown",
                        issue_type="schema_discovery_failed",
                        severity="critical",
                        confidence=1.0,
                        suggested_fix="Inspect the live schema and update the words allowlist before rerunning the words audit.",
                        explanation="Words tables could not be confidently discovered from the allowlisted schema candidates.",
                        evidence={"sources": discovery.words_tables, "similarity_score": None, "semantic_relation": None, "top_alternatives": [], "rule_checks": discovery.notes, "llm_used": False, "llm_model": None},
                        human_review_required=True,
                    )
                )
                run.coverage.records_skipped += 1
            else:
                words_repo = GuardedRepository(
                    conn,
                    guardrails,
                    RepositoryContext("words", frozenset(discovery.words_tables)),
                )
                findings.extend(
                    audit_words(
                        run_id=run.run_id,
                        repository=words_repo,
                        coverage=run.coverage,
                        confidence_policy=config.confidence_policy,
                        llm_fallback_policy=config.llm_fallback_policy,
                        schema_summary=run.schema_summary,
                        limit=limit,
                    )
                )

        run.findings = findings
        run.coverage.deterministic_coverage_pct = 100.0 if run.coverage.records_checked else 0.0
        run.coverage.semantic_coverage_pct = 100.0 if config.openai_api_key else 0.0
        run.coverage.overall_coverage_pct = (run.coverage.deterministic_coverage_pct + run.coverage.semantic_coverage_pct) / 2

        run.completed_at = datetime.now(timezone.utc).isoformat()
        payload = _serialize_run(run)
        diff = build_diff(payload["findings"], _previous_findings(config.reports_dir))
        write_reports(reports_dir=config.reports_dir, run_id=run.run_id, run_payload=payload, diff_payload=diff)
        return payload
    finally:
        conn.close()


def _serialize_run(run: AuditRun) -> dict:
    payload = run.to_dict()
    for finding in payload["findings"]:
        finding["identity_key"] = "|".join(
            [finding["app"], finding["table_name"], str(finding["record_id"]), finding["issue_type"], finding["current_value"]]
        )
    return payload
