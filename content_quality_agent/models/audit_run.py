"""Run-level model for a content quality audit."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from content_quality_agent.models.coverage import CoverageReport
from content_quality_agent.models.finding import Finding


@dataclass
class AuditRun:
    run_id: str
    mode: str
    dry_run: bool
    started_at: str
    completed_at: str | None
    reports_dir: str
    llm_available: bool
    findings: list[Finding] = field(default_factory=list)
    coverage: CoverageReport = field(default_factory=CoverageReport)
    errors: list[dict] = field(default_factory=list)
    guardrail_status: str = "ok"
    schema_summary: dict = field(default_factory=dict)
    skipped_checks: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["findings"] = [finding.to_dict() for finding in self.findings]
        payload["coverage"] = self.coverage.to_dict()
        return payload
