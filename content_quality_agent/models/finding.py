"""Finding model used across all reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Evidence:
    sources: list[str] = field(default_factory=list)
    similarity_score: float | None = None
    semantic_relation: str | None = None
    top_alternatives: list[str] = field(default_factory=list)
    rule_checks: list[str] = field(default_factory=list)
    llm_used: bool = False
    llm_model: str | None = None


@dataclass
class Finding:
    run_id: str
    app: str
    table_name: str
    record_id: str
    lesson_id: int | None
    pattern_id: int | None
    word: str | None
    headword: str | None
    current_value: str
    issue_type: str
    severity: str
    confidence: float
    suggested_fix: str
    explanation: str
    evidence: Evidence
    human_review_required: bool = True

    def identity_key(self) -> str:
        return "|".join(
            [
                self.app,
                self.table_name,
                str(self.record_id),
                self.issue_type,
                self.current_value,
            ]
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["evidence"] = asdict(self.evidence)
        return payload
