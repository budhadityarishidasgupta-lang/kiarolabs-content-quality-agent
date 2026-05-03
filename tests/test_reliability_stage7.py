import csv
import json
import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from content_quality_agent.reports.atomic_write import atomic_write_csv, atomic_write_json, atomic_write_text
from content_quality_agent.reports.writer import write_reports
from content_quality_agent.runner import generate_run_id


def _payload(run_id: str):
    return {
        "run_id": run_id,
        "mode": "all",
        "dry_run": True,
        "started_at": "2026-05-03T20:41:43+00:00",
        "completed_at": "2026-05-03T20:41:44+00:00",
        "reports_dir": "reports",
        "guardrail_status": "ok",
        "findings": [],
        "coverage": {
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
            "semantic_coverage_pct": 0.0,
            "overall_coverage_pct": 50.0,
        },
    }


class ReliabilityStage7Tests(unittest.TestCase):
    def test_two_generated_run_ids_in_same_second_are_unique(self):
        now = datetime(2026, 5, 3, 20, 41, 43, tzinfo=timezone.utc)
        with patch("content_quality_agent.runner.secrets.token_hex", side_effect=["a1b2c3d4", "e5f6a7b8"]):
            first = generate_run_id(now)
            second = generate_run_id(now)
        self.assertNotEqual(first, second)

    def test_run_id_format_matches_expected_pattern(self):
        now = datetime(2026, 5, 3, 20, 41, 43, tzinfo=timezone.utc)
        with patch("content_quality_agent.runner.secrets.token_hex", return_value="a1b2c3d4"):
            run_id = generate_run_id(now)
        self.assertRegex(run_id, r"^audit-\d{8}-\d{6}-[0-9a-f]{8}$")

    def test_atomic_write_helpers_write_valid_text_json_and_csv(self):
        tmp_dir = Path("tests") / "_tmp_stage7_atomic"
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            text_path = tmp_dir / "sample.txt"
            json_path = tmp_dir / "sample.json"
            csv_path = tmp_dir / "sample.csv"
            atomic_write_text(text_path, "hello")
            atomic_write_json(json_path, {"ok": True})
            atomic_write_csv(csv_path, ["name", "value"], [{"name": "alpha", "value": "1"}])
            self.assertEqual("hello", text_path.read_text(encoding="utf-8"))
            self.assertTrue(json.loads(json_path.read_text(encoding="utf-8"))["ok"])
            rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual("alpha", rows[0]["name"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_latest_run_json_points_to_correct_run_id_and_run_dir(self):
        tmp_dir = Path("tests") / "_tmp_stage7_writer"
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            reports_dir = tmp_dir / "reports"
            run_id = "audit-20260503-204143-a1b2c3d4"
            write_reports(
                reports_dir=reports_dir,
                run_id=run_id,
                run_payload=_payload(run_id),
                diff_payload={"new_findings": [], "persisting_findings": [], "resolved_findings": []},
            )
            latest = json.loads((reports_dir / "latest-run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_id, latest["run_id"])
            self.assertTrue(str(reports_dir / "runs" / run_id).endswith(latest["source_run_dir"].replace("/", "\\")) or latest["source_run_dir"] == str(reports_dir / "runs" / run_id))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_manifest_exists_and_contains_required_fields(self):
        tmp_dir = Path("tests") / "_tmp_stage7_manifest"
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            reports_dir = tmp_dir / "reports"
            run_id = "audit-20260503-204143-a1b2c3d4"
            write_reports(
                reports_dir=reports_dir,
                run_id=run_id,
                run_payload=_payload(run_id),
                diff_payload={"new_findings": [], "persisting_findings": [], "resolved_findings": []},
            )
            manifest = json.loads((reports_dir / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
            for key in ("run_id", "mode", "dry_run", "started_at", "completed_at", "reports_written", "latest_files_updated", "findings_count", "score_summary", "coverage_summary"):
                self.assertIn(key, manifest)
            self.assertEqual(run_id, manifest["run_id"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_report_writer_writes_run_files_before_latest_metadata(self):
        tmp_dir = Path("tests") / "_tmp_stage7_order"
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            reports_dir = tmp_dir / "reports"
            run_id = "audit-20260503-204143-a1b2c3d4"
            recorded_paths: list[str] = []

            def _recording_atomic_write_text(path, content):
                recorded_paths.append(str(path))
                atomic_write_text(path, content)

            def _recording_atomic_write_json(path, payload):
                recorded_paths.append(str(path))
                atomic_write_json(path, payload)

            with patch("content_quality_agent.reports.writer.atomic_write_text", side_effect=_recording_atomic_write_text), patch(
                "content_quality_agent.reports.writer.atomic_write_json", side_effect=_recording_atomic_write_json
            ):
                write_reports(
                    reports_dir=reports_dir,
                    run_id=run_id,
                    run_payload=_payload(run_id),
                    diff_payload={"new_findings": [], "persisting_findings": [], "resolved_findings": []},
                )

            latest_run_index = recorded_paths.index(str(reports_dir / "latest-run.json"))
            self.assertLess(recorded_paths.index(str(reports_dir / "runs" / run_id / "content-quality-report.md")), latest_run_index)
            self.assertLess(recorded_paths.index(str(reports_dir / "runs" / run_id / "manifest.json")), latest_run_index)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
