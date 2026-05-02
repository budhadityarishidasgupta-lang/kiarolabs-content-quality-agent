"""Coverage model for audit runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CoverageReport:
    total_records_discovered: int = 0
    records_checked: int = 0
    records_skipped: int = 0
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: list[str] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)
    llm_available: bool = False
    deterministic_coverage_pct: float = 0.0
    semantic_coverage_pct: float = 0.0
    overall_coverage_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)
