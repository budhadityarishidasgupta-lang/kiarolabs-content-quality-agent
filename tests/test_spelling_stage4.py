import csv
import json
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from content_quality_agent.auditors import spelling_auditor as spelling_module
from content_quality_agent.models.coverage import CoverageReport
from content_quality_agent.reports.writer import write_reports


class _Repo:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _sql, _params=None):
        return list(self.rows)


class SpellingStage4Tests(unittest.TestCase):
    def test_course_id_1_does_not_trigger_pattern_cleanup_logic(self):
        rows = [
            (1, 1, "action", "", "Action is important.", 101, '"OLD" pattern Words', '"OLD" pattern Words'),
        ]
        coverage = CoverageReport()
        findings = spelling_module.audit_spelling(run_id="audit-1", repository=_Repo(rows), coverage=coverage, limit=10)
        self.assertFalse(any(f.issue_type == "pattern_assignment_mismatch" for f in findings))

    def test_course_id_9_can_trigger_pattern_cleanup_logic(self):
        rows = [
            (2, 9, "action", "", "Action is important.", 102, '"OLD" pattern Words', '"OLD" pattern Words'),
        ]
        coverage = CoverageReport()
        findings = spelling_module.audit_spelling(run_id="audit-2", repository=_Repo(rows), coverage=coverage, limit=10)
        self.assertTrue(any(f.issue_type == "pattern_assignment_mismatch" for f in findings))

    def test_allowlist_suppresses_matching_hint_finding(self):
        rows = [
            (3, 9, "adventure", "remember this clue", "Adventure awaits.", 103, '"URE" pattern Words', '"URE" pattern Words'),
        ]
        coverage = CoverageReport()
        original_loader = spelling_module.load_false_positive_allowlist
        try:
            spelling_module.load_false_positive_allowlist = lambda: {
                "suppressions": [
                    {
                        "issue_type": "hint_relevance_weak",
                        "word": "adventure",
                        "current_value_contains": "remember",
                        "reason": "known safe clue variant",
                    }
                ]
            }
            findings = spelling_module.audit_spelling(run_id="audit-3", repository=_Repo(rows), coverage=coverage, limit=10)
        finally:
            spelling_module.load_false_positive_allowlist = original_loader
        self.assertEqual([], findings)
        self.assertEqual(1, coverage.suppressed_findings)
        self.assertTrue(any("suppressed by allowlist" in note for note in coverage.notes))

    def test_suppressed_findings_are_excluded_from_review_queue(self):
        tmp_root = Path(tempfile.gettempdir()) / f"content-quality-stage4-{uuid.uuid4().hex}"
        reports_dir = tmp_root / "reports"
        payload = {
            "run_id": "audit-20260503-120000",
            "mode": "spelling",
            "dry_run": True,
            "started_at": "2026-05-03T12:00:00Z",
            "reports_dir": str(reports_dir),
            "guardrail_status": "ok",
            "findings": [],
            "coverage": {
                "total_records_discovered": 1,
                "records_checked": 1,
                "records_skipped": 0,
                "suppressed_findings": 1,
                "checks_run": [],
                "checks_skipped": [],
                "skip_reasons": [],
                "notes": ["1 findings suppressed by allowlist (pronunciation clue is valid)."],
                "llm_available": False,
                "deterministic_coverage_pct": 100.0,
                "semantic_coverage_pct": 0.0,
                "overall_coverage_pct": 50.0,
            },
        }
        try:
            write_reports(reports_dir=reports_dir, run_id=payload["run_id"], run_payload=payload, diff_payload=None)
            review_queue_rows = list(csv.DictReader((reports_dir / "review-queue-latest.csv").read_text(encoding="utf-8").splitlines()))
            self.assertEqual([], review_queue_rows)
            latest_json = json.loads((reports_dir / "content-quality-latest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, latest_json["coverage"]["suppressed_findings"])
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
