import unittest

from content_quality_agent.intelligence.false_positive_filter import should_suppress_finding


class FalsePositiveFilterTests(unittest.TestCase):
    def test_matching_hint_finding_is_suppressed(self):
        suppressed, reason = should_suppress_finding(
            {
                "issue_type": "hint_relevance_weak",
                "word": "adventure",
                "lesson_id": 9,
                "current_value": "ure sounds like cher",
            },
            {
                "suppressions": [
                    {
                        "issue_type": "hint_relevance_weak",
                        "word": "adventure",
                        "current_value_contains": "cher",
                        "reason": "pronunciation clue is valid",
                    }
                ]
            },
        )
        self.assertTrue(suppressed)
        self.assertEqual("pronunciation clue is valid", reason)

    def test_non_matching_hint_finding_is_not_suppressed(self):
        suppressed, reason = should_suppress_finding(
            {
                "issue_type": "hint_relevance_weak",
                "word": "adventure",
                "lesson_id": 9,
                "current_value": "remember the ending",
            },
            {
                "suppressions": [
                    {
                        "issue_type": "hint_relevance_weak",
                        "word": "adventure",
                        "current_value_contains": "cher",
                        "reason": "pronunciation clue is valid",
                    }
                ]
            },
        )
        self.assertFalse(suppressed)
        self.assertIsNone(reason)
