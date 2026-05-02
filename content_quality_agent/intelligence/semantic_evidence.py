"""Deterministic and optional semantic evidence helpers."""

from __future__ import annotations

from difflib import SequenceMatcher
import re

from content_quality_agent.models.finding import Evidence


WORD_RE = re.compile(r"[a-zA-Z]+")


def tokenize(value: str | None) -> list[str]:
    if not value:
        return []
    return [token.lower() for token in WORD_RE.findall(value)]


def similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def build_rule_evidence(*, sources: list[str] | None = None, rule_checks: list[str] | None = None, top_alternatives: list[str] | None = None, similarity_score: float | None = None, semantic_relation: str | None = None) -> Evidence:
    return Evidence(
        sources=sources or [],
        rule_checks=rule_checks or [],
        top_alternatives=top_alternatives or [],
        similarity_score=similarity_score,
        semantic_relation=semantic_relation,
        llm_used=False,
        llm_model=None,
    )
