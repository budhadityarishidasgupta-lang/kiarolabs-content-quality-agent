import unittest

from content_quality_agent.auditors.spelling_auditor import _hint_is_relevant, _word_matches_lesson_pattern


class SpellingAuditorRuleTests(unittest.TestCase):
    def test_action_in_ion_lesson_passes(self):
        self.assertTrue(_word_matches_lesson_pattern("action", '"ION" ending spelling pattern'))

    def test_education_in_ion_lesson_passes(self):
        self.assertTrue(_word_matches_lesson_pattern("education", '"ION" ending spelling pattern'))

    def test_fiction_in_ion_lesson_passes(self):
        self.assertTrue(_word_matches_lesson_pattern("fiction", '"ION" ending spelling pattern'))

    def test_adventure_in_ure_lesson_passes(self):
        self.assertTrue(_word_matches_lesson_pattern("adventure", '"URE" ending spelling pattern'))

    def test_furniture_in_ure_lesson_passes(self):
        self.assertTrue(_word_matches_lesson_pattern("furniture", '"URE" ending spelling pattern'))

    def test_knighthood_in_ure_lesson_fails(self):
        self.assertFalse(_word_matches_lesson_pattern("knighthood", '"URE" ending spelling pattern'))

    def test_neighbourhood_in_ure_lesson_fails(self):
        self.assertFalse(_word_matches_lesson_pattern("neighbourhood", '"URE" ending spelling pattern'))

    def test_physiology_in_ure_lesson_fails(self):
        self.assertFalse(_word_matches_lesson_pattern("physiology", '"URE" ending spelling pattern'))

    def test_ure_sounds_like_cher_hint_passes(self):
        self.assertTrue(_hint_is_relevant("creature", "ure sounds like cher", '"URE" ending spelling pattern'))

    def test_bio_means_life_hint_passes(self):
        self.assertTrue(_hint_is_relevant("biology", "bio means life", "Greek and Latin roots"))
