"""Spelling content quality auditor."""

from __future__ import annotations

from collections import defaultdict
import re

from content_quality_agent.intelligence.pattern_detector import detect_spelling_pattern
from content_quality_agent.intelligence.semantic_evidence import build_rule_evidence, tokenize
from content_quality_agent.models.finding import Finding


KNOWN_PATTERNS = ("ph", "gh", "tion", "sion", "ough", "dge", "tch", "ck", "wr", "kn")
PATTERN_HINT_KEYWORDS = {
    "pattern",
    "suffix",
    "prefix",
    "root",
    "meaning",
    "pronunciation",
    "pronounce",
    "sound",
    "silent",
    "letter",
    "tricky",
    "ends",
    "ending",
    "unstressed",
    "means",
}
ROOT_HINT_PATTERNS = {
    "bio": ("bio", "life"),
}


def _extract_patterns(word: str) -> list[str]:
    lowered = (word or "").lower()
    return [pattern for pattern in KNOWN_PATTERNS if pattern in lowered]


def _normalize_lesson_label(label: str) -> str:
    cleaned = (label or "").lower()
    cleaned = cleaned.replace('"', " ").replace("'", " ")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _canonical_pattern_tokens(label: str) -> set[str]:
    normalized = _normalize_lesson_label(label)
    tokens = set(tokenize(normalized))
    canonical: set[str] = set(tokens)

    if "ion" in normalized.split() or '"ion"' in (label or "").lower():
        canonical.update({"ion_family", "ion", "tion", "sion", "cion"})
    if "ure" in normalized.split() or '"ure"' in (label or "").lower():
        canonical.update({"ure_family", "ure"})
    return canonical


def _word_matches_lesson_pattern(word: str, label: str) -> bool:
    lowered = (word or "").lower()
    canonical = _canonical_pattern_tokens(label)
    if not canonical:
        return True

    if "ion_family" in canonical:
        return lowered.endswith(("ion", "tion", "sion", "cion"))
    if "ure_family" in canonical:
        return lowered.endswith("ure")

    patterns = _extract_patterns(word)
    if patterns:
        return any(pattern in canonical for pattern in patterns)
    return True


def _hint_is_relevant(word: str, hint: str, lesson_label: str) -> bool:
    if not hint:
        return True
    hint_lower = hint.lower()
    word_lower = (word or "").lower()
    canonical = _canonical_pattern_tokens(lesson_label)

    if word_lower and word_lower in hint_lower:
        return True
    if any(keyword in hint_lower for keyword in PATTERN_HINT_KEYWORDS):
        return True
    if "ion_family" in canonical and any(token in hint_lower for token in ("ion", "tion", "sion", "cion")):
        return True
    if "ure_family" in canonical and "ure" in hint_lower:
        return True
    if word_lower.endswith("ure") and ("cher" in hint_lower or "unstressed" in hint_lower):
        return True
    for root, clues in ROOT_HINT_PATTERNS.items():
        if root in word_lower and any(clue in hint_lower for clue in clues):
            return True
    return False


def audit_spelling(*, run_id: str, repository, coverage, limit: int | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rows = repository.query(
        """
        SELECT
            w.word_id,
            w.course_id,
            w.word,
            COALESCE(w.hint, ''),
            COALESCE(w.example_sentence, ''),
            li.lesson_id,
            COALESCE(l.lesson_name, ''),
            COALESCE(l.display_name, l.lesson_name, '')
        FROM public.spelling_words w
        JOIN public.spelling_lesson_items li
            ON li.word_id = w.word_id
        JOIN public.spelling_lessons l
            ON l.lesson_id = li.lesson_id
        WHERE COALESCE(l.is_active, TRUE) = TRUE
        ORDER BY li.lesson_id ASC, w.word_id ASC
        LIMIT %s
        """,
        (limit or 200,),
    )
    coverage.total_records_discovered += len(rows)
    coverage.records_checked += len(rows)
    coverage.checks_run.extend(
        [
            "spelling.pattern_assignment",
            "spelling.hint_relevance",
            "spelling.example_relevance",
            "spelling.pattern_outlier_detection",
        ]
    )

    by_lesson: dict[int, list[tuple]] = defaultdict(list)
    for row in rows:
        by_lesson[row[5]].append(row)

    for word_id, course_id, word, hint, example_sentence, lesson_id, lesson_name, display_name in rows:
        patterns = _extract_patterns(word)
        effective_label = display_name or lesson_name
        detector_result = detect_spelling_pattern(word, hint=hint, current_pattern=effective_label)
        pattern_mismatch = not _word_matches_lesson_pattern(word, effective_label)
        if course_id == 9 and detector_result.detected_pattern and detector_result.canonical_lesson_name != effective_label:
            pattern_mismatch = True
        if pattern_mismatch:
            suggested_fix = (
                f"Move '{word}' to {detector_result.canonical_lesson_name}."
                if course_id == 9 and detector_result.canonical_lesson_name != "UNASSIGNED"
                else f"Review whether '{word}' belongs in lesson '{effective_label}'."
            )
            findings.append(
                Finding(
                    run_id=run_id,
                    app="spelling",
                    table_name="public.spelling_words",
                    record_id=str(word_id),
                    lesson_id=lesson_id,
                    pattern_id=None,
                    word=word,
                    headword=None,
                    current_value=effective_label,
                    issue_type="pattern_assignment_mismatch",
                    severity="high",
                    confidence=max(0.9, detector_result.confidence),
                    suggested_fix=suggested_fix,
                    explanation="Detected spelling pattern in word does not match the normalized lesson pattern." if detector_result.canonical_lesson_name == "UNASSIGNED" else f"Detected spelling pattern suggests {detector_result.canonical_lesson_name}, which does not match the current lesson.",
                    evidence=build_rule_evidence(
                        sources=["public.spelling_words.word", "public.spelling_lessons.display_name"],
                        top_alternatives=list(dict.fromkeys([*patterns, *( [detector_result.detected_pattern.lower()] if detector_result.detected_pattern else [] )])),
                        rule_checks=["word_pattern_missing_from_normalized_lesson_label", *detector_result.evidence],
                    ),
                    human_review_required=True,
                )
            )
        if hint and not _hint_is_relevant(word, hint, effective_label):
            findings.append(
                Finding(
                    run_id=run_id,
                    app="spelling",
                    table_name="public.spelling_words",
                    record_id=str(word_id),
                    lesson_id=lesson_id,
                    pattern_id=None,
                    word=word,
                    headword=None,
                    current_value=hint,
                    issue_type="hint_relevance_weak",
                    severity="medium",
                    confidence=0.84,
                    suggested_fix=f"Strengthen hint for '{word}' so it connects to the word meaning or spelling pattern.",
                    explanation="Hint does not appear to reference the spelling pattern, pronunciation, root meaning, or a useful semantic clue.",
                    evidence=build_rule_evidence(
                        sources=["public.spelling_words.hint"],
                        top_alternatives=patterns,
                        rule_checks=["hint_missing_pattern_pronunciation_or_semantic_clue"],
                    ),
                    human_review_required=True,
                )
            )
        if not example_sentence:
            findings.append(
                Finding(
                    run_id=run_id,
                    app="spelling",
                    table_name="public.spelling_words",
                    record_id=str(word_id),
                    lesson_id=lesson_id,
                    pattern_id=None,
                    word=word,
                    headword=None,
                    current_value="",
                    issue_type="missing_example_sentence",
                    severity="medium",
                    confidence=0.98,
                    suggested_fix=f"Add an example sentence for '{word}'.",
                    explanation="Target word is missing an example sentence.",
                    evidence=build_rule_evidence(
                        sources=["public.spelling_words.example_sentence"],
                        rule_checks=["example_sentence_missing"],
                    ),
                    human_review_required=True,
                )
            )
        elif word.lower() not in example_sentence.lower():
            findings.append(
                Finding(
                    run_id=run_id,
                    app="spelling",
                    table_name="public.spelling_words",
                    record_id=str(word_id),
                    lesson_id=lesson_id,
                    pattern_id=None,
                    word=word,
                    headword=None,
                    current_value=example_sentence,
                    issue_type="example_sentence_unrelated",
                    severity="high",
                    confidence=0.87,
                    suggested_fix=f"Rewrite the example sentence so '{word}' appears clearly in context.",
                    explanation="Example sentence does not appear to contain the target word.",
                    evidence=build_rule_evidence(
                        sources=["public.spelling_words.example_sentence"],
                        rule_checks=["example_sentence_missing_target_word"],
                    ),
                    human_review_required=True,
                )
            )

    for lesson_id, lesson_rows in by_lesson.items():
        lesson_pattern_sets = [_extract_patterns(row[2]) for row in lesson_rows if _extract_patterns(row[2])]
        if not lesson_pattern_sets:
            continue
        common = set(lesson_pattern_sets[0]).intersection(*map(set, lesson_pattern_sets[1:])) if len(lesson_pattern_sets) > 1 else set(lesson_pattern_sets[0])
        if not common:
            word_id, _, word, _, _, _, lesson_name, display_name = lesson_rows[0]
            findings.append(
                Finding(
                    run_id=run_id,
                    app="spelling",
                    table_name="public.spelling_lesson_items",
                    record_id=str(lesson_id),
                    lesson_id=lesson_id,
                    pattern_id=None,
                    word=word,
                    headword=None,
                    current_value=display_name or lesson_name,
                    issue_type="pattern_group_outlier_set",
                    severity="high",
                    confidence=0.82,
                    suggested_fix="Review this lesson group for inconsistent pattern membership.",
                    explanation="Words within the lesson do not share a stable detected spelling pattern.",
                    evidence=build_rule_evidence(
                        sources=["public.spelling_lesson_items", "public.spelling_words"],
                        top_alternatives=sorted({pattern for patterns in lesson_pattern_sets for pattern in patterns}),
                        rule_checks=["lesson_pattern_intersection_empty"],
                    ),
                    human_review_required=True,
                )
            )

    return findings
