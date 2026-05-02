"""Deterministic spelling-pattern detection for pattern lesson audits and fixes."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


CANONICAL_PATTERN_RE = re.compile(r'^"[A-Z0-9/\' -]+" pattern Words$')


@dataclass(frozen=True)
class PatternDetectionResult:
    word: str
    detected_pattern: str | None
    canonical_lesson_name: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    needs_review: bool = True


def canonical_lesson_name_for_pattern(pattern: str | None) -> str:
    if not pattern:
        return "UNASSIGNED"
    normalized = normalize_pattern_token(pattern)
    if not normalized:
        return "UNASSIGNED"
    return f'"{normalized}" pattern Words'


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


def detect_spelling_pattern(word: str, hint: str | None = None, current_pattern: str | None = None) -> PatternDetectionResult:
    lowered = (word or "").strip().lower()
    hint_lower = (hint or "").strip().lower()
    current_normalized = extract_canonical_pattern_from_lesson_name(current_pattern)
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
    suffix_rules: list[tuple[str, str, float]] = [
        ("ssion", "SSION", 0.99),
        ("tion", "TION", 0.98),
        ("sion", "SION", 0.96),
        ("ship", "SHIP", 0.98),
        ("hood", "HOOD", 0.98),
        ("cide", "CIDE", 0.98),
        ("ology", "OLOGY", 0.98),
        ("iness", "INESS", 0.98),
        ("ure", "URE", 0.95),
        ("ful", "FUL/LESS", 0.96),
        ("less", "FUL/LESS", 0.96),
        ("ing", "ING", 0.88),
        ("ly", "LY", 0.86),
        ("ous", "OUS", 0.9),
        ("our", "OUR", 0.9),
        ("or", "OR", 0.82),
        ("ic", "IC", 0.82),
    ]
    for suffix, pattern, confidence in suffix_rules:
        if lowered.endswith(suffix):
            evidence.append(f"suffix:{suffix}")
            return _build_result(word, pattern, confidence, evidence, current_normalized)

    # Phonics/spelling groups
    phonics_rules: list[tuple[str, str, float]] = [
        ("dge", "DGE", 0.97),
        ("ph", "PH", 0.93),
        ("ch", "CH", 0.91),
        ("gh", "GH", 0.9),
    ]
    for needle, pattern, confidence in phonics_rules:
        if needle in lowered:
            evidence.append(f"contains:{needle}")
            return _build_result(word, pattern, confidence, evidence, current_normalized)

    if lowered.endswith("ed"):
        evidence.append("suffix:ed")
        return _build_result(word, "D/ED", 0.78, evidence, current_normalized, needs_review=True)

    if "c" in lowered:
        evidence.append("contains:c")
        return _build_result(word, "C", 0.7, evidence, current_normalized, needs_review=True)

    if "'" in lowered or "ps" in lowered:
        evidence.append("contains:apostrophe_or_ps")
        return _build_result(word, "P'S", 0.65, evidence, current_normalized, needs_review=True)

    if current_normalized and current_normalized != "UNASSIGNED":
        evidence.append(f"fallback_current_pattern:{current_normalized}")
        return _build_result(word, current_normalized, 0.55, evidence, current_normalized, needs_review=True)

    if hint_lower:
        for token, pattern in (("life", "OLOGY"), ("silent", "GH"), ("cher", "URE")):
            if token in hint_lower:
                evidence.append(f"hint:{token}")
                return _build_result(word, pattern, 0.6, evidence, current_normalized, needs_review=True)

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
    *,
    needs_review: bool | None = None,
) -> PatternDetectionResult:
    canonical = canonical_lesson_name_for_pattern(pattern)
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
