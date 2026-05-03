"""Classify Words schema and content shape before auditing."""

from __future__ import annotations

from dataclasses import dataclass, field

from content_quality_agent.intelligence.semantic_relation import classify_candidate_relation


OPTION_COLUMN_TOKENS = ("option", "choice", "distractor", "answer_a", "answer_b", "answer_c", "answer_d")


@dataclass(frozen=True)
class WordsSchemaClassification:
    classification: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    expected_correct_answer_column: str | None = None
    option_columns: list[str] = field(default_factory=list)
    synonym_columns: list[str] = field(default_factory=list)
    warning_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "expected_correct_answer_column": self.expected_correct_answer_column,
            "option_columns": list(self.option_columns),
            "synonym_columns": list(self.synonym_columns),
            "warning_notes": list(self.warning_notes),
        }


def _contains_option_columns(columns: set[str]) -> list[str]:
    return sorted(
        column for column in columns
        if any(token in column.lower() for token in OPTION_COLUMN_TOKENS)
    )


def classify_words_schema(
    schema_summary: dict,
    sample_rows: list[dict] | None = None,
    preferred_source_table: str | None = None,
) -> WordsSchemaClassification:
    table_columns = schema_summary.get("table_columns", {})
    public_words = set(table_columns.get("public.words", []))
    legacy_words = set(table_columns.get("public.words_words", []))

    public_option_columns = _contains_option_columns(public_words)
    legacy_option_columns = _contains_option_columns(legacy_words)

    allow_legacy = preferred_source_table in (None, "public.words_words")
    allow_public = preferred_source_table in (None, "public.words")

    if allow_legacy and {"id", "word", "correct_answer"}.issubset(legacy_words):
        return WordsSchemaClassification(
            classification="legacy_words_content",
            confidence=0.93,
            evidence=["table:public.words_words", "columns:word+correct_answer"],
            expected_correct_answer_column="correct_answer",
            option_columns=legacy_option_columns,
            synonym_columns=[],
            warning_notes=["Legacy Words content detected; auditing correct_answer only."],
        )

    if allow_public and (
        {"word_id", "headword", "correct_answer"}.issubset(public_words)
        or ({"word_id", "headword"}.issubset(public_words) and public_option_columns)
    ):
        return WordsSchemaClassification(
            classification="multiple_choice_options",
            confidence=0.9,
            evidence=["table:public.words", "columns:headword+correct_answer/options"],
            expected_correct_answer_column="correct_answer" if "correct_answer" in public_words else None,
            option_columns=public_option_columns,
            synonym_columns=["synonyms"] if "synonyms" in public_words else [],
            warning_notes=["Multiple-choice style Words content detected."],
        )

    if allow_public and {"word_id", "headword", "synonyms"}.issubset(public_words) and not public_option_columns and "correct_answer" not in public_words:
        warning_notes: list[str] = []
        evidence = ["table:public.words", "columns:headword+synonyms", "no_option_or_correct_answer_columns"]
        classification = "pure_synonym_content"
        confidence = 0.72

        if sample_rows:
            checked = 0
            antonym_hits = 0
            for row in sample_rows:
                headword = str(row.get("headword", "") or "")
                synonym_blob = str(row.get("synonyms", "") or "")
                candidates = [item.strip() for item in synonym_blob.split(",") if item.strip()]
                if not candidates:
                    continue
                checked += 1
                for candidate in candidates[:3]:
                    relation = classify_candidate_relation(headword, candidate)
                    if relation.relation == "likely_antonym" and relation.confidence >= 0.9:
                        antonym_hits += 1
                        evidence.append(f"candidate_antonym:{headword}->{candidate}")
                        break
            hit_threshold = max(2, int(checked * 0.1)) if checked else 2
            if antonym_hits >= hit_threshold:
                classification = "mixed_content_unknown"
                confidence = 0.9
                warning_notes.append("Sampled synonym values contain likely antonym/distractor options.")
            elif checked:
                evidence.append(f"sample_rows_checked:{checked}")

        return WordsSchemaClassification(
            classification=classification,
            confidence=confidence,
            evidence=evidence,
            expected_correct_answer_column=None,
            option_columns=[],
            synonym_columns=["synonyms"],
            warning_notes=warning_notes,
        )

    if (allow_public and public_words) or (allow_legacy and legacy_words):
        return WordsSchemaClassification(
            classification="mixed_content_unknown",
            confidence=0.55,
            evidence=["words_columns_present_but_shape_ambiguous"],
            expected_correct_answer_column="correct_answer" if "correct_answer" in public_words else None,
            option_columns=public_option_columns or legacy_option_columns,
            synonym_columns=[name for name in ("synonyms",) if name in public_words],
            warning_notes=["Words schema/content shape is ambiguous; findings should be capped."],
        )

    return WordsSchemaClassification(
        classification="unsupported_schema",
        confidence=1.0,
        evidence=["no_supported_words_source"],
        expected_correct_answer_column=None,
        option_columns=[],
        synonym_columns=[],
        warning_notes=["Words schema is unsupported for safe auditing."],
    )
