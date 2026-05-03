"""Deterministic spelling-pattern detection for pattern lesson audits and fixes."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from content_quality_agent.intelligence.spelling_rules import (
    canonical_lesson_name_for_pattern as config_canonical_lesson_name_for_pattern,
    get_contains_rules,
    get_hint_clue_rules,
    get_low_confidence_rules,
    get_priority_suffix_rules,
    load_spelling_rules,
)


CANONICAL_PATTERN_RE = re.compile(r'^"[A-Z0-9/\' -]+" pattern Words$')


@dataclass(frozen=True)
class PatternDetectionResult:
    word: str
    detected_pattern: str | None
    canonical_lesson_name: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    needs_review: bool = True


def canonical_lesson_name_for_pattern(pattern: str | None, rules: dict | None = None) -> str:
    if not pattern:
        return "UNASSIGNED"
    normalized = normalize_pattern_token(pattern)
    if not normalized:
        return "UNASSIGNED"
    active_rules = rules or load_spelling_rules()
    return config_canonical_lesson_name_for_pattern(normalized, active_rules)


def normalize_pattern_token(pattern: str | None) -> str | None:
    if not pattern:
        return None
    cleaned = pattern.strip().upper().replace('"', "")
    cleaned = re.sub(r"\s+", "", cleaned)
    if cleaned in {"", "PATTERN", "WORDS"}:
        return None
    return cleaned


def extract_canonical_pattern_from_lesson_name(label: str | None) -> str | None:
    if not label:
        return None
    candidate = label.strip()
    if candidate == "UNASSIGNED":
        return "UNASSIGNED"
    match = re.match(r'^"([^"]+)"\s+pattern\s+Words$', candidate, re.IGNORECASE)
    if not match:
        return normalize_pattern_token(candidate)
    return normalize_pattern_token(match.group(1))


def validate_canonical_lesson_name(lesson_name: str) -> bool:
    return lesson_name == "UNASSIGNED" or bool(CANONICAL_PATTERN_RE.match(lesson_name))


def detect_spelling_pattern(word: str, hint: str | None = None, current_pattern: str | None = None, rules: dict | None = None) -> PatternDetectionResult:
    lowered = (word or "").strip().lower()
    hint_lower = (hint or "").strip().lower()
    current_normalized = extract_canonical_pattern_from_lesson_name(current_pattern)
    active_rules = rules or load_spelling_rules()
    evidence: list[str] = []

    if not lowered:
        return PatternDetectionResult(
            word=word,
            detected_pattern=None,
            canonical_lesson_name="UNASSIGNED",
            confidence=0.0,
            evidence=["word_missing"],
            needs_review=True,
        )

    # Priority suffix families
    for rule in get_priority_suffix_rules(active_rules):
        suffix = rule["suffix"]
        if lowered.endswith(suffix):
            evidence.extend([f"suffix:{suffix}", "config_rule:priority_suffix_rules"])
            return _build_result(word, rule["pattern"], rule["confidence"], evidence, current_normalized, active_rules)

    for rule in get_contains_rules(active_rules):
        needle = rule["contains"]
        if needle in lowered:
            evidence.extend([f"contains:{needle}", "config_rule:contains_rules"])
            return _build_result(word, rule["pattern"], rule["confidence"], evidence, current_normalized, active_rules)

    for rule in get_low_confidence_rules(active_rules):
        suffix = rule.get("suffix")
        contains = rule.get("contains")
        if suffix and lowered.endswith(suffix):
            evidence.extend([f"suffix:{suffix}", "config_rule:low_confidence_rules"])
            return _build_result(word, rule["pattern"], rule["confidence"], evidence, current_normalized, active_rules, needs_review=True)
        if contains and contains in lowered:
            evidence.extend([f"contains:{contains}", "config_rule:low_confidence_rules"])
            return _build_result(word, rule["pattern"], rule["confidence"], evidence, current_normalized, active_rules, needs_review=True)

    if current_normalized and current_normalized != "UNASSIGNED":
        evidence.append(f"fallback_current_pattern:{current_normalized}")
        return _build_result(word, current_normalized, 0.55, evidence, current_normalized, active_rules, needs_review=True)

    if hint_lower:
        for rule in get_hint_clue_rules(active_rules):
            token = rule["hint_contains"]
            if token in hint_lower:
                evidence.extend([f"hint:{token}", "config_rule:hint_clue_rules"])
                return _build_result(word, rule["pattern"], rule["confidence"], evidence, current_normalized, active_rules, needs_review=True)

    return PatternDetectionResult(
        word=word,
        detected_pattern=None,
        canonical_lesson_name="UNASSIGNED",
        confidence=0.0,
        evidence=["no_confident_pattern_detected"],
        needs_review=True,
    )


def _build_result(
    word: str,
    pattern: str,
    confidence: float,
    evidence: list[str],
    current_normalized: str | None,
    rules: dict,
    *,
    needs_review: bool | None = None,
) -> PatternDetectionResult:
    canonical = canonical_lesson_name_for_pattern(pattern, rules)
    normalized = normalize_pattern_token(pattern)
    review = needs_review if needs_review is not None else confidence < 0.8
    if current_normalized and current_normalized == normalized:
        evidence = [*evidence, "matches_current_pattern"]
        confidence = min(0.999, confidence + 0.01)
    return PatternDetectionResult(
        word=word,
        detected_pattern=normalized,
        canonical_lesson_name=canonical,
        confidence=confidence,
        evidence=evidence,
        needs_review=review,
    )
