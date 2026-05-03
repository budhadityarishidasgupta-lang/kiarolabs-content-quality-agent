import io
import json
import unittest
from contextlib import redirect_stdout

from content_quality_agent import cli as cli_module
from content_quality_agent.auditors.words_auditor import audit_words
from content_quality_agent.intelligence.semantic_relation import classify_candidate_relation
from content_quality_agent.intelligence.words_schema_classifier import classify_words_schema
from content_quality_agent.models.coverage import CoverageReport


class _Repo:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _sql, _params=None):
        return list(self.rows)


PURE_SCHEMA = {
    "table_columns": {
        "public.words": ["word_id", "headword", "synonyms"],
        "public.lesson_words": ["lesson_id", "word_id"],
        "public.lessons": ["lesson_id"],
    }
}

LEGACY_SCHEMA = {
    "table_columns": {
        "public.words_words": ["id", "word", "correct_answer"],
        "public.words_lesson_words": ["lesson_id", "word_id"],
        "public.words_lessons": ["id"],
    }
}

MULTIPLE_CHOICE_SCHEMA = {
    "table_columns": {
        "public.words": ["word_id", "headword", "correct_answer", "option_a", "option_b", "option_c"],
        "public.lesson_words": ["lesson_id", "word_id"],
        "public.lessons": ["lesson_id"],
    }
}

BOTH_WORDS_SCHEMAS = {
    "table_columns": {
        "public.words": ["word_id", "headword", "synonyms"],
        "public.words_words": ["id", "word", "correct_answer"],
        "public.lesson_words": ["lesson_id", "word_id"],
        "public.lessons": ["lesson_id"],
        "public.words_lesson_words": ["lesson_id", "word_id"],
        "public.words_lessons": ["id"],
    }
}


class WordsStage6Tests(unittest.TestCase):
    def test_classifier_detects_pure_synonym_content(self):
        result = classify_words_schema(PURE_SCHEMA, [{"headword": "happy", "synonyms": "glad, cheerful"}])
        self.assertEqual("pure_synonym_content", result.classification)

    def test_classifier_detects_multiple_choice_options(self):
        result = classify_words_schema(MULTIPLE_CHOICE_SCHEMA)
        self.assertEqual("multiple_choice_options", result.classification)

    def test_classifier_detects_legacy_words_content(self):
        result = classify_words_schema(LEGACY_SCHEMA)
        self.assertEqual("legacy_words_content", result.classification)

    def test_classifier_prefers_audited_public_words_source_when_both_tables_exist(self):
        sample_rows = [{"headword": "hot", "synonyms": "cold, warm, dry"} for _ in range(10)]
        result = classify_words_schema(BOTH_WORDS_SCHEMAS, sample_rows, preferred_source_table="public.words")
        self.assertEqual("mixed_content_unknown", result.classification)

    def test_classifier_returns_mixed_content_unknown_when_ambiguous(self):
        sample_rows = [{"headword": "hot", "synonyms": "cold, warm, dry"} for _ in range(10)]
        result = classify_words_schema(PURE_SCHEMA, sample_rows)
        self.assertEqual("mixed_content_unknown", result.classification)

    def test_hot_cold_relation_is_likely_antonym(self):
        self.assertEqual("likely_antonym", classify_candidate_relation("hot", "cold").relation)

    def test_happy_sad_relation_is_likely_antonym(self):
        self.assertEqual("likely_antonym", classify_candidate_relation("happy", "sad").relation)

    def test_happy_glad_relation_is_likely_synonym_or_related(self):
        self.assertIn(classify_candidate_relation("happy", "glad").relation, {"likely_synonym", "related_but_not_synonym"})

    def test_mixed_content_mode_caps_findings_to_policy_limit(self):
        rows = [(index, "hot", "cold, warm, dry", "", "", None) for index in range(100)]
        coverage = CoverageReport()
        findings = audit_words(
            run_id="audit-words-1",
            repository=_Repo(rows),
            coverage=coverage,
            confidence_policy={},
            llm_fallback_policy={"words.ambiguous_headword_detection": "skipped_if_no_llm"},
            schema_summary=PURE_SCHEMA,
            limit=100,
        )
        self.assertLessEqual(len(findings), 25)
        self.assertEqual("mixed_content_unknown", coverage.words_schema_classification)
        self.assertGreater(coverage.capped_findings, 0)

    def test_mixed_content_mode_does_not_emit_weak_synonym_flood(self):
        rows = [(index, "hot", "cold, warm, dry", "", "", None) for index in range(200)]
        coverage = CoverageReport()
        findings = audit_words(
            run_id="audit-words-2",
            repository=_Repo(rows),
            coverage=coverage,
            confidence_policy={},
            llm_fallback_policy={"words.ambiguous_headword_detection": "skipped_if_no_llm"},
            schema_summary=PURE_SCHEMA,
            limit=200,
        )
        self.assertFalse(any(f.issue_type == "weak_synonym_mapping" for f in findings))
        self.assertLessEqual(len(findings), 25)

    def test_pure_synonym_mode_can_still_emit_strong_bad_mapping(self):
        rows = [(1, "hot", "cold", "", "", None)]
        coverage = CoverageReport()
        findings = audit_words(
            run_id="audit-words-3",
            repository=_Repo(rows),
            coverage=coverage,
            confidence_policy={},
            llm_fallback_policy={"words.ambiguous_headword_detection": "skipped_if_no_llm"},
            schema_summary=PURE_SCHEMA,
            limit=1,
        )
        self.assertEqual("pure_synonym_content", coverage.words_schema_classification)
        self.assertTrue(any(f.issue_type == "weak_synonym_mapping" for f in findings))

    def test_dry_run_still_passes(self):
        original_run_audit = cli_module.run_audit
        try:
            cli_module.run_audit = lambda **_kwargs: {
                "run_id": "audit-stage6",
                "mode": "all",
                "dry_run": True,
                "findings": [],
                "reports_dir": "reports",
            }
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = cli_module.main(["--mode", "all", "--dry-run"])
        finally:
            cli_module.run_audit = original_run_audit
        self.assertEqual(0, exit_code)
        payload = json.loads(stream.getvalue())
        self.assertTrue(payload["dry_run"])
