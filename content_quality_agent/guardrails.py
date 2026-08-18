"""Read-only guardrails for database access."""

from __future__ import annotations

from dataclasses import dataclass
import re


WRITE_KEYWORDS = ("insert", "update", "delete", "alter", "create", "drop", "truncate")
TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?",
    re.IGNORECASE,
)


class GuardrailViolation(RuntimeError):
    """Raised when a query violates read-only or table-isolation rules."""


@dataclass(frozen=True)
class GuardrailContext:
    app: str
    allowed_tables: frozenset[str]


class GuardrailEnforcer:
    """Enforces permanent read-only database access and per-app isolation."""

    def __init__(self, phase: str = "audit_only") -> None:
        self.phase = phase

    def validate(self, sql: str, context: GuardrailContext) -> None:
        normalized = " ".join(sql.strip().split())
        lowered = normalized.lower()
        if not lowered.startswith("select "):
            raise GuardrailViolation("Content audit agent blocks all non-SELECT SQL.")
        if any(keyword in lowered for keyword in WRITE_KEYWORDS):
            raise GuardrailViolation("Content audit agent blocks all write or DDL statements.")

        referenced = self._extract_tables(normalized)
        if not referenced:
            raise GuardrailViolation("Query did not reference an allowed table explicitly.")

        for table in referenced:
            if table not in context.allowed_tables:
                raise GuardrailViolation(
                    f"Table '{table}' is not allowed for app '{context.app}'."
                )

        if context.app == "spelling" and any(not table.startswith("public.spelling_") for table in referenced):
            raise GuardrailViolation("Spelling auditor may only read spelling_* tables.")
        if context.app == "math" and any(not table.startswith("public.math_") for table in referenced):
            raise GuardrailViolation("Math auditor may only read math_* tables.")
        if context.app == "vr" and any(not table.startswith("public.vr_") for table in referenced):
            raise GuardrailViolation("VR auditor may only read vr_* tables.")
        if context.app == "words":
            if any(table.startswith(("public.spelling_", "public.math_", "public.vr_")) for table in referenced):
                raise GuardrailViolation("Words auditor may not read another app namespace.")

    def validate_mutation(self, sql: str, context: GuardrailContext) -> None:
        raise GuardrailViolation(
            "Content quality agent is audit-only. Database mutations are permanently disabled; "
            "human-approved corrections must use the owning app's CSV/admin ingestion workflow."
        )

    def _extract_tables(self, sql: str) -> set[str]:
        tables: set[str] = set()
        for match in TABLE_REF_RE.finditer(sql):
            left = match.group(1)
            right = match.group(2)
            if right:
                tables.add(f"{left.lower()}.{right.lower()}")
            else:
                tables.add(f"public.{left.lower()}")
        return tables
