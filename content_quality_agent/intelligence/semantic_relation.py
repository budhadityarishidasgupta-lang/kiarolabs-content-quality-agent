"""Deterministic relation classification for Words audit candidates."""

from __future__ import annotations

from dataclasses import dataclass, field

from content_quality_agent.intelligence.semantic_evidence import similarity


@dataclass(frozen=True)
class SemanticRelationResult:
    relation: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


def _pair(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted(((left or "").strip().lower(), (right or "").strip().lower())))


ANTONYM_CLUES = {
    _pair("hot", "cold"),
    _pair("big", "small"),
    _pair("happy", "sad"),
    _pair("light", "dark"),
    _pair("up", "down"),
    _pair("loud", "quiet"),
    _pair("day", "night"),
    _pair("early", "late"),
    _pair("full", "empty"),
    _pair("high", "low"),
}

SYNONYM_CLUES = {
    _pair("happy", "glad"),
    _pair("big", "large"),
    _pair("light", "bright"),
    _pair("day", "morning"),
    _pair("full", "filled"),
}


def classify_candidate_relation(headword: str | None, candidate: str | None) -> SemanticRelationResult:
    left = (headword or "").strip().lower()
    right = (candidate or "").strip().lower()
    if not left or not right:
        return SemanticRelationResult("unknown", 0.0, ["missing_headword_or_candidate"])

    if left == right:
        return SemanticRelationResult("likely_synonym", 0.98, ["exact_match"])

    pair = _pair(left, right)
    if pair in ANTONYM_CLUES:
        return SemanticRelationResult("likely_antonym", 0.97, [f"antonym_clue:{left}/{right}"])
    if pair in SYNONYM_CLUES:
        return SemanticRelationResult("likely_synonym", 0.9, [f"synonym_clue:{left}/{right}"])

    lexical_similarity = similarity(left, right)
    if lexical_similarity >= 0.85:
        return SemanticRelationResult("likely_synonym", 0.82, [f"lexical_similarity:{lexical_similarity:.2f}"])
    if lexical_similarity >= 0.45:
        return SemanticRelationResult("related_but_not_synonym", 0.62, [f"lexical_similarity:{lexical_similarity:.2f}"])
    return SemanticRelationResult("unknown", 0.35, [f"lexical_similarity:{lexical_similarity:.2f}"])
