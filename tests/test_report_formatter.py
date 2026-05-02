import json
import unittest

from content_quality_agent.reports.formatter import format_csv_rows, format_json, format_markdown


class ReportFormatterTests(unittest.TestCase):
    def test_report_formatter_outputs_markdown_json_csv(self):
        payload = {
            "run_id": "audit-20260501-120000",
            "mode": "all",
            "dry_run": False,
            "started_at": "2026-05-01T12:00:00Z",
            "reports_dir": "reports",
            "guardrail_status": "ok",
            "findings": [],
            "coverage": {
                "total_records_discovered": 0,
                "records_checked": 0,
                "records_skipped": 0,
                "checks_skipped": [],
                "llm_available": False,
                "deterministic_coverage_pct": 0.0,
                "semantic_coverage_pct": 0.0,
                "overall_coverage_pct": 0.0,
            },
        }
        self.assertIn("# Content Quality Audit Report", format_markdown(payload, None))
        self.assertEqual(json.loads(format_json(payload))["run_id"], payload["run_id"])
        csv_out = format_csv_rows([])
        self.assertIn("run_id,app,severity", csv_out)
