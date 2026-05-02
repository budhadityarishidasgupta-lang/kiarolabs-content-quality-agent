import unittest

from content_quality_agent.intelligence.pattern_detector import detect_spelling_pattern


class PatternDetectorTests(unittest.TestCase):
    def assert_pattern(self, word: str, expected: str, hint: str | None = None):
        result = detect_spelling_pattern(word, hint=hint)
        self.assertEqual(result.canonical_lesson_name, expected)

    def test_action_maps_to_tion(self):
        self.assert_pattern("action", '"TION" pattern Words')

    def test_education_maps_to_tion(self):
        self.assert_pattern("education", '"TION" pattern Words')

    def test_tension_maps_to_sion(self):
        self.assert_pattern("tension", '"SION" pattern Words')

    def test_admission_maps_to_ssion(self):
        self.assert_pattern("admission", '"SSION" pattern Words')

    def test_adventure_maps_to_ure(self):
        self.assert_pattern("adventure", '"URE" pattern Words')

    def test_friendship_maps_to_ship(self):
        self.assert_pattern("friendship", '"SHIP" pattern Words')

    def test_childhood_maps_to_hood(self):
        self.assert_pattern("childhood", '"HOOD" pattern Words')

    def test_biology_maps_to_ology(self):
        self.assert_pattern("biology", '"OLOGY" pattern Words')

    def test_physics_maps_to_ph(self):
        self.assert_pattern("physics", '"PH" pattern Words')

    def test_trophy_maps_to_ph(self):
        self.assert_pattern("trophy", '"PH" pattern Words')

    def test_bridge_maps_to_dge(self):
        self.assert_pattern("bridge", '"DGE" pattern Words')

    def test_happiness_maps_to_iness(self):
        self.assert_pattern("happiness", '"INESS" pattern Words')

    def test_useful_maps_to_ful_less(self):
        self.assert_pattern("useful", '"FUL/LESS" pattern Words')

    def test_careless_maps_to_ful_less(self):
        self.assert_pattern("careless", '"FUL/LESS" pattern Words')

    def test_unknown_pattern_becomes_unassigned(self):
        result = detect_spelling_pattern("table")
        self.assertEqual(result.canonical_lesson_name, "UNASSIGNED")
        self.assertTrue(result.needs_review)
