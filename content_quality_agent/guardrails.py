"""Read-only guardrails for database access."""

from __future__ import annotations

from dataclasses import dataclass
import re


WRITE_KEYWORDS = ("insert", "update", "delete", "alter", "create", "drop", "truncate")
TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?",
    re.IGNORECASE,
)
UPDATE_REF_RE = re.compile(
    r"^\s*update\s+([a-zA-Z_][\w]*)(?:\.([a-zA-Z_][\w]*))?",
    re.IGNORECASE,
)


class GuardrailViolation(RuntimeError):
    """Raised when a query violates read-only or table-isolation rules."""


@dataclass(frozen=True)
class GuardrailContext:
    app: str
    allowed_tables: frozenset[str]


class GuardrailEnforcer:
    """Ensures phase-1 read-only database access."""

    def __init__(self, phase: str = "phase_1") -> None:
        self.phase = phase

    def validate(self, sql: str, context: GuardrailContext) -> None:
        normalized = " ".join(sql.strip().split())
        lowered = normalized.lower()
        if not lowered.startswith("select "):
            raise GuardrailViolation("Phase 1 blocks non-SELECT SQL.")
        if any(keyword in lowered for keyword in WRITE_KEYWORDS):
            raise GuardrailViolation("Phase 1 blocks write or DDL statements.")

        referenced = self._extract_tables(normalized)
        if not referenced:
            raise GuardrailViolation("Query did not reference an allowed table explicitly.")

        for table in referenced:
            if table not in context.allowed_tables:
                raise GuardrailViolation(
                    f"Table '{table}' is not allowed for app '{context.app}'."
                )

        prefixes = {table.split(".", 1)[1].split("_", 1)[0] for table in referenced}
        if context.app == "spelling" and any(not table.startswith("public.spelling_") for table in referenced):
            raise GuardrailViolation("Spelling auditor may only read spelling_* tables.")
        if context.app == "words":
            if any(table.startswith("public.spelling_") for table in referenced):
                raise GuardrailViolation("Words auditor may not read spelling_* tables.")
            if len(prefixes) > 3:
                raise GuardrailViolation("Potential cross-app read detected in words query.")

    def validate_mutation(self, sql: str, context: GuardrailContext) -> None:
        normalized = " ".join(sql.strip().split())
        lowered = normalized.lower()
        if self.phase == "phase_1":
            raise GuardrailViolation("Phase 1 blocks all write SQL.")
        if not lowered.startswith("update "):
            raise GuardrailViolation("Phase 2 fix workflow only allows UPDATE statements.")
        if any(keyword in lowered for keyword in ("insert", "delete", "alter", "create", "drop", "truncate")):
            raise GuardrailViolation("Phase 2 fix workflow only allows narrowly-scoped UPDATE statements.")

        match = UPDATE_REF_RE.match(normalized)
        if not match:
            raise GuardrailViolation("Mutation query did not reference an allowed table explicitly.")

        left = match.group(1)
        right = match.group(2)
        table = f"{left.lower()}.{right.lower()}" if right else f"public.{left.lower()}"
        if table not in context.allowed_tables:
            raise GuardrailViolation(f"Table '{table}' is not allowed for app '{context.app}'.")
        if context.app != "spelling" or table != "public.spelling_words":
            raise GuardrailViolation("Phase 2 spelling fixes may only update public.spelling_words.")

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
