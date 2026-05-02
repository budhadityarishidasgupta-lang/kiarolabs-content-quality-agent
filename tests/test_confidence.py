import unittest

from content_quality_agent.intelligence.confidence import classify_confidence


POLICY = {
    "strong_recommendation": 0.95,
    "human_review": 0.8,
    "informational": 0.6,
}


class ConfidenceTests(unittest.TestCase):
    def test_confidence_thresholds_classify_correctly(self):
        self.assertEqual(classify_confidence(0.96, POLICY), "strong_recommendation")
        self.assertEqual(classify_confidence(0.84, POLICY), "human_review")
        self.assertEqual(classify_confidence(0.7, POLICY), "informational")
        self.assertEqual(classify_confidence(0.4, POLICY), "ignore")
