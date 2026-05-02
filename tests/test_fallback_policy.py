import unittest

from content_quality_agent.intelligence.fallback import fallback_mode, semantic_checks_partial
from content_quality_agent.reports.diff import build_diff


class FallbackAndDiffTests(unittest.TestCase):
    def test_llm_fallback_reports_partial(self):
        policy = {"words.synonym_semantic_closeness": "degraded"}
        self.assertEqual(fallback_mode(policy, "words.synonym_semantic_closeness"), "degraded")
        self.assertTrue(semantic_checks_partial(policy, llm_available=False))

    def test_diff_logic_identifies_new_persisting_resolved(self):
        current = [
            {"identity_key": "a", "issue_type": "x"},
            {"identity_key": "b", "issue_type": "y"},
        ]
        previous = [
            {"identity_key": "b", "issue_type": "y"},
            {"identity_key": "c", "issue_type": "z"},
        ]
        diff = build_diff(current, previous)
        self.assertEqual([item["identity_key"] for item in diff["new_findings"]], ["a"])
        self.assertEqual([item["identity_key"] for item in diff["persisting_findings"]], ["b"])
        self.assertEqual([item["identity_key"] for item in diff["resolved_findings"]], ["c"])
