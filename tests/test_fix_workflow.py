import csv
import unittest
from pathlib import Path
import shutil

from content_quality_agent.fix_workflow import _validate_fix_row, generate_spelling_lesson_fix_suggestions
from content_quality_agent.config import RuntimeConfig


class _StubRepository:
    def __init__(self, records):
        self.records = records

    def fetch_spelling_word_for_update(self, record_id: int):
        return self.records.get(record_id)

    def fetch_spelling_words_for_fix_candidates(self, record_ids: list[int]):
        return [self.records[record_id] for record_id in record_ids if record_id in self.records]


class FixWorkflowTests(unittest.TestCase):
    def test_validate_fix_row_rejects_wrong_course(self):
        repo = _StubRepository(
            {
                1: {
                    "record_id": 1,
                    "course_id": 1,
                    "word": "action",
                    "hint": "",
                    "lesson_name": '"OLD" pattern Words',
                }
            }
        )
        result = _validate_fix_row(
            repo,
            {
                "app": "spelling",
                "table_name": "public.spelling_words",
                "record_id": "1",
                "current_value": '"OLD" pattern Words',
                "approved_value": '"TION" pattern Words',
                "fix_type": "spelling_lesson_name_correction",
                "approved_by": "tester",
                "approval_timestamp": "2026-05-01T10:00:00Z",
            },
        )
        self.assertFalse(result.valid)
        self.assertIn("course_id must be 9", result.errors)

    def test_validate_fix_row_accepts_course9_canonical(self):
        repo = _StubRepository(
            {
                9: {
                    "record_id": 9,
                    "course_id": 9,
                    "word": "action",
                    "hint": "",
                    "lesson_name": '"OLD" pattern Words',
                }
            }
        )
        result = _validate_fix_row(
            repo,
            {
                "app": "spelling",
                "table_name": "public.spelling_words",
                "record_id": "9",
                "current_value": '"OLD" pattern Words',
                "approved_value": '"TION" pattern Words',
                "fix_type": "spelling_lesson_name_correction",
                "approved_by": "tester",
                "approval_timestamp": "2026-05-01T10:00:00Z",
            },
        )
        self.assertTrue(result.valid)

    def test_generate_suggestions_filters_to_course9(self):
        tmp = Path(__file__).resolve().parents[1] / "tests" / "_tmp_fix_workflow"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            source = tmp / "findings.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "run_id",
                        "app",
                        "severity",
                        "confidence",
                        "issue_type",
                        "table_name",
                        "record_id",
                        "lesson_id",
                        "pattern_id",
                        "word",
                        "headword",
                        "current_value",
                        "suggested_fix",
                        "explanation",
                        "human_review_required",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "run_id": "audit-1",
                        "app": "spelling",
                        "severity": "high",
                        "confidence": "0.9",
                        "issue_type": "pattern_assignment_mismatch",
                        "table_name": "public.spelling_words",
                        "record_id": "9",
                        "lesson_id": "",
                        "pattern_id": "",
                        "word": "action",
                        "headword": "",
                        "current_value": '"OLD" pattern Words',
                        "suggested_fix": "",
                        "explanation": "",
                        "human_review_required": "True",
                    }
                )

            config = RuntimeConfig(
                db_url="stub",
                openai_api_key=None,
                reports_dir=tmp / "reports",
                fail_on=("critical", "high"),
                audit_config={},
                table_allowlist={},
                confidence_policy={},
                llm_fallback_policy={},
            )

            # We exercise CSV writing separately from DB calls by monkeypatching locally.
            from content_quality_agent import fix_workflow as module

            original_connect = module.connect
            original_repo = module.GuardedRepository
            try:
                class _Conn:
                    def close(self):
                        return None

                module.connect = lambda _dsn: _Conn()

                class _RepoFactory(_StubRepository):
                    def __init__(self, *_args, **_kwargs):
                        super().__init__(
                            {
                                9: {
                                    "record_id": 9,
                                    "course_id": 9,
                                    "word": "action",
                                    "hint": "",
                                    "lesson_name": '"OLD" pattern Words',
                                }
                            }
                        )

                module.GuardedRepository = _RepoFactory
                payload = generate_spelling_lesson_fix_suggestions(config=config, source_path=source)
            finally:
                module.connect = original_connect
                module.GuardedRepository = original_repo

            self.assertEqual(payload["suggestions"], 1)
            self.assertTrue(Path(payload["output"]).exists())
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
