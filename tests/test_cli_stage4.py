import io
import json
import unittest
from contextlib import redirect_stdout

from content_quality_agent import cli as cli_module


class CliStage4Tests(unittest.TestCase):
    def test_dry_run_mode_still_passes(self):
        original_run_audit = cli_module.run_audit
        try:
            cli_module.run_audit = lambda **_kwargs: {
                "run_id": "audit-stage4",
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
        self.assertEqual("all", payload["mode"])
