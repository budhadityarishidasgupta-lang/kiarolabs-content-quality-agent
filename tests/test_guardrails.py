import unittest

from content_quality_agent.guardrails import GuardrailContext, GuardrailEnforcer, GuardrailViolation


class GuardrailTests(unittest.TestCase):
    def test_guardrails_block_write_sql(self):
        guardrails = GuardrailEnforcer()
        context = GuardrailContext(app="spelling", allowed_tables=frozenset({"public.spelling_words"}))
        with self.assertRaises(GuardrailViolation):
            guardrails.validate("UPDATE spelling_words SET word = 'x'", context)

    def test_guardrails_block_unknown_table(self):
        guardrails = GuardrailEnforcer()
        context = GuardrailContext(app="spelling", allowed_tables=frozenset({"public.spelling_words"}))
        with self.assertRaises(GuardrailViolation):
            guardrails.validate("SELECT * FROM public.words", context)

    def test_guardrails_allow_spelling_read(self):
        guardrails = GuardrailEnforcer()
        context = GuardrailContext(app="spelling", allowed_tables=frozenset({"public.spelling_words"}))
        guardrails.validate("SELECT word FROM public.spelling_words", context)

    def test_phase2_allows_spelling_update(self):
        guardrails = GuardrailEnforcer(phase="phase_2")
        context = GuardrailContext(app="spelling", allowed_tables=frozenset({"public.spelling_words"}))
        guardrails.validate_mutation(
            "UPDATE public.spelling_words SET lesson_name = '\"TION\" pattern Words' WHERE word_id = 1",
            context,
        )
