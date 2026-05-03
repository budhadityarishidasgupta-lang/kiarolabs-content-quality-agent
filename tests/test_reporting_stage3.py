import csv
import json
import unittest
import uuid
import shutil
from pathlib import Path

from content_quality_agent.reports.review_queue import REVIEW_QUEUE_COLUMNS, format_review_queue_csv
from content_quality_agent.reports.scoring import calculate_scores
from content_quality_agent.reports.writer import write_reports


def _base_payload(findings=None, coverage=None):
    return {
        "run_id": "audit-20260502-120000",
        "mode": "all",
        "dry_run": True,
        "started_at": "2026-05-02T12:00:00Z",
        "reports_dir": "reports",
        "guardrail_status": "ok",
        "findings": findings or [],
        "coverage": coverage
        or {
            "total_records_discovered": 10,
            "records_checked": 10,
            "records_skipped": 0,
            "suppressed_findings": 0,
            "capped_findings": 0,
            "checks_run": [],
            "checks_skipped": [],
            "skip_reasons": [],
            "notes": [],
            "words_schema_classification": None,
            "words_schema_confidence": 0.0,
            "words_audit_partial": False,
            "schema_unclear_should_not_collapse_score": False,
            "llm_available": False,
            "deterministic_coverage_pct": 100.0,
            "semantic_coverage_pct": 100.0,
            "overall_coverage_pct": 100.0,
        },
    }


def _finding(severity="medium", app="spelling", confidence=0.9):
    return {
        "run_id": "audit-20260502-120000",
        "app": app,
        "table_name": "public.spelling_words",
        "record_id": "42",
        "lesson_id": 9,
        "pattern_id": 1,
        "word": "action",
        "headword": None,
        "current_value": '"ION" pattern Words',
        "issue_type": "pattern_assignment_mismatch",
        "severity": severity,
        "confidence": confidence,
        "suggested_fix": '"TION" pattern Words',
        "explanation": "Example explanation.",
        "evidence": {},
        "human_review_required": True,
    }


class ReportingStage3Tests(unittest.TestCase):
    def test_scoring_returns_100_for_no_findings_and_full_coverage(self):
        scores = calculate_scores(_base_payload())
        self.assertEqual(100, scores["overall_content_quality_score"])
        self.assertEqual(100, scores["spelling_score"])
        self.assertEqual(100, scores["words_score"])

    def test_scoring_does_not_return_100_for_no_findings_but_poor_coverage(self):
        payload = _base_payload(
            coverage={
                "total_records_discovered": 10,
                "records_checked": 0,
                "records_skipped": 10,
                "suppressed_findings": 0,
                "capped_findings": 0,
                "checks_run": [],
                "checks_skipped": ["semantic_review"],
                "skip_reasons": ["LLM unavailable"],
                "notes": [],
                "words_schema_classification": None,
                "words_schema_confidence": 0.0,
                "words_audit_partial": False,
                "schema_unclear_should_not_collapse_score": False,
                "llm_available": False,
                "deterministic_coverage_pct": 0.0,
                "semantic_coverage_pct": 0.0,
                "overall_coverage_pct": 40.0,
            }
        )
        scores = calculate_scores(payload)
        self.assertLess(scores["overall_content_quality_score"], 100)

    def test_critical_findings_reduce_score_more_than_medium_findings(self):
        critical = calculate_scores(_base_payload(findings=[_finding(severity="critical")]))
        medium = calculate_scores(_base_payload(findings=[_finding(severity="medium")]))
        self.assertLess(critical["overall_content_quality_score"], medium["overall_content_quality_score"])

    def test_scores_are_clamped_between_0_and_100(self):
        findings = [_finding(severity="critical", confidence=1.0) for _ in range(20)]
        scores = calculate_scores(_base_payload(findings=findings))
        for value in scores.values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_review_queue_csv_contains_all_required_columns(self):
        csv_payload = format_review_queue_csv([_finding()])
        reader = csv.DictReader(csv_payload.splitlines())
        self.assertEqual(REVIEW_QUEUE_COLUMNS, reader.fieldnames)

    def test_review_queue_preserves_finding_details(self):
        csv_payload = format_review_queue_csv([_finding(app="words", severity="high")])
        row = next(csv.DictReader(csv_payload.splitlines()))
        self.assertEqual("words", row["app"])
        self.assertEqual("high", row["severity"])
        self.assertEqual("action", row["word"])
        self.assertEqual("Example explanation.", row["explanation"])

    def test_review_queue_does_not_require_approved_value(self):
        csv_payload = format_review_queue_csv([_finding()])
        row = next(csv.DictReader(csv_payload.splitlines()))
        self.assertEqual("", row["approved_value"])
        self.assertEqual("", row["human_decision"])

    def test_writer_outputs_review_queue_and_score_block(self):
        payload = _base_payload(findings=[_finding(severity="high"), _finding(app="words", severity="low")])
        diff_payload = {"new_findings": [], "persisting_findings": [], "resolved_findings": []}
        tmp_root = Path("tests") / f"_tmp_writer_stage3_{uuid.uuid4().hex}"
        reports_dir = tmp_root / "reports"
        try:
            write_reports(
                reports_dir=reports_dir,
                run_id=payload["run_id"],
                run_payload=payload,
                diff_payload=diff_payload,
            )
            latest_json = json.loads((reports_dir / "content-quality-latest.json").read_text(encoding="utf-8"))
            self.assertIn("scores", latest_json)
            self.assertTrue((reports_dir / "review-queue-latest.csv").exists())
            self.assertTrue((reports_dir / "executive-summary-latest.md").exists())
            self.assertIn("Overall Content Quality Score", (reports_dir / "content-quality-latest.md").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
