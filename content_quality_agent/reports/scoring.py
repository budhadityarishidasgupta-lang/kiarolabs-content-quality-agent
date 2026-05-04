"""Content-quality scoring helpers for audit reporting."""

from __future__ import annotations

from typing import Iterable


SEVERITY_WEIGHTS = {
    "critical": 20,
    "high": 10,
    "medium": 4,
    "low": 1,
}

SCHEMA_SHAPE_WARNING_TYPES = {
    "words_content_shape_unclear",
    "possible_distractor_column_misread_as_synonym_list",
}


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _finding_weight(finding: dict, coverage: dict | None = None) -> float:
    base = float(SEVERITY_WEIGHTS.get(finding.get("severity", "low"), 1))
    if (
        coverage
        and coverage.get("words_schema_classification") == "mixed_content_unknown"
        and coverage.get("schema_unclear_should_not_collapse_score")
        and finding.get("issue_type") in SCHEMA_SHAPE_WARNING_TYPES
    ):
        return 0.5
    return base


def _severity_penalty(findings: Iterable[dict], coverage: dict | None = None) -> int:
    total = 0.0
    for finding in findings:
        total += _finding_weight(finding, coverage)
    return _clamp_score(total)


def _confidence_adjusted_risk_score(findings: Iterable[dict], coverage: dict | None = None) -> int:
    total = 0.0
    for finding in findings:
        weight = _finding_weight(finding, coverage)
        confidence = float(finding.get("confidence", 0.0) or 0.0)
        total += weight * confidence
    return _clamp_score(total)


def _coverage_penalty(coverage: dict) -> int:
    overall = float(coverage.get("overall_coverage_pct", 0.0) or 0.0)
    checks_skipped = coverage.get("checks_skipped", []) or []
    penalty = max(0.0, (100.0 - overall) * 0.2)
    if checks_skipped:
        penalty += min(10.0, len(checks_skipped) * 2.0)
    return _clamp_score(penalty)


def _score_for_app(findings: list[dict], coverage_penalty: int, app: str, coverage: dict) -> int:
    app_findings = [finding for finding in findings if finding.get("app") == app]
    severity_penalty = _severity_penalty(app_findings, coverage)
    return _clamp_score(100 - severity_penalty - coverage_penalty)


def calculate_scores(run_payload: dict) -> dict[str, int]:
    """Calculate quality scores from findings and coverage without mutating data."""

    findings = run_payload.get("findings", [])
    coverage = run_payload.get("coverage", {})

    severity_penalty = _severity_penalty(findings, coverage)
    coverage_penalty = _coverage_penalty(coverage)
    confidence_adjusted_risk_score = _confidence_adjusted_risk_score(findings, coverage)

    overall_content_quality_score = _clamp_score(100 - severity_penalty - coverage_penalty)
    spelling_score = _score_for_app(findings, coverage_penalty, "spelling", coverage)
    words_score = _score_for_app(findings, coverage_penalty, "words", coverage)

    return {
        "overall_content_quality_score": overall_content_quality_score,
        "spelling_score": spelling_score,
        "words_score": words_score,
        "severity_penalty": severity_penalty,
        "coverage_penalty": coverage_penalty,
        "confidence_adjusted_risk_score": confidence_adjusted_risk_score,
    }
