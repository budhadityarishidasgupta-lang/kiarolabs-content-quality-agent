"""Words content quality auditor."""

from __future__ import annotations

from content_quality_agent.intelligence.fallback import fallback_mode
from content_quality_agent.intelligence.semantic_evidence import build_rule_evidence, similarity, tokenize
from content_quality_agent.models.finding import Finding


def _resolve_words_source(schema_summary: dict) -> dict | None:
    table_columns = schema_summary.get("table_columns", {})

    public_words = set(table_columns.get("public.words", []))
    if {"word_id", "headword", "synonyms"}.issubset(public_words):
        return {
            "source_table": "public.words",
            "id_column": "word_id",
            "headword_column": "headword",
            "synonym_column": "synonyms",
            "antonym_column": "antonyms" if "antonyms" in public_words else None,
            "compound_column": "compound_word" if "compound_word" in public_words else None,
            "lesson_join": """
                LEFT JOIN public.lesson_words lw
                    ON lw.word_id = w.word_id
                LEFT JOIN public.lessons l
                    ON l.lesson_id = lw.lesson_id
            """,
            "lesson_id_column": "l.lesson_id",
        }

    legacy_words = set(table_columns.get("public.words_words", []))
    if {"id", "word", "correct_answer"}.issubset(legacy_words):
        return {
            "source_table": "public.words_words",
            "id_column": "id",
            "headword_column": "word",
            "synonym_column": "correct_answer",
            "antonym_column": None,
            "compound_column": None,
            "lesson_join": """
                LEFT JOIN public.words_lesson_words lw
                    ON lw.word_id = w.id
                LEFT JOIN public.words_lessons l
                    ON l.id = lw.lesson_id
            """,
            "lesson_id_column": "l.id",
        }

    return None


def audit_words(*, run_id: str, repository, coverage, confidence_policy: dict, llm_fallback_policy: dict, schema_summary: dict, limit: int | None = None) -> list[Finding]:
    findings: list[Finding] = []
    source = _resolve_words_source(schema_summary)
    if not source:
        coverage.records_skipped += 1
        coverage.checks_skipped.extend(
            [
                "words.synonym_semantic_closeness",
                "words.antonym_semantic_opposition",
                "words.compound_word_validity",
            ]
        )
        coverage.skip_reasons.append("Words source table columns were not sufficient for a safe audit query.")
        return [
            Finding(
                run_id=run_id,
                app="words",
                table_name="schema.discovery",
                record_id="words-columns",
                lesson_id=None,
                pattern_id=None,
                word=None,
                headword=None,
                current_value="words_source_unresolved",
                issue_type="schema_discovery_failed",
                severity="critical",
                confidence=1.0,
                suggested_fix="Confirm the live Words content table shape and update the allowlist/source mapping.",
                explanation="Words audit could not resolve a safe source table and column mapping from discovered schema.",
                evidence=build_rule_evidence(
                    sources=list((schema_summary.get("table_columns") or {}).keys()),
                    rule_checks=["words_source_resolution_failed"],
                ),
                human_review_required=True,
            )
        ]

    synonym_sql = source["synonym_column"]
    antonym_sql = source["antonym_column"]
    compound_sql = source["compound_column"]
    lesson_join = source["lesson_join"]
    lesson_id_column = source["lesson_id_column"]

    select_parts = [
        f"w.{source['id_column']}",
        f"COALESCE(w.{source['headword_column']}, '')",
        f"COALESCE(w.{synonym_sql}, '')",
        "''" if antonym_sql is None else f"COALESCE(w.{antonym_sql}, '')",
        "''" if compound_sql is None else f"COALESCE(w.{compound_sql}, '')",
        lesson_id_column,
    ]

    rows = repository.query(
        f"""
        SELECT
            {", ".join(select_parts)}
        FROM {source['source_table']} w
        {lesson_join}
        ORDER BY w.{source['id_column']} ASC
        LIMIT %s
        """,
        (limit or 200,),
    )
    coverage.total_records_discovered += len(rows)
    coverage.records_checked += len(rows)
    coverage.checks_run.extend(
        [
            "words.synonym_semantic_closeness",
            *(["words.antonym_semantic_opposition"] if antonym_sql else []),
            *(["words.compound_word_validity"] if compound_sql else []),
        ]
    )
    if antonym_sql is None:
        coverage.checks_skipped.append("words.antonym_semantic_opposition")
        coverage.skip_reasons.append("Words source table does not expose an antonyms column.")
    if compound_sql is None:
        coverage.checks_skipped.append("words.compound_word_validity")
        coverage.skip_reasons.append("Words source table does not expose a compound_word column.")

    ambiguity_mode = fallback_mode(llm_fallback_policy, "words.ambiguous_headword_detection")
    ambiguity_skip_logged = False

    for word_id, headword, synonyms, antonyms, compound_word, lesson_id in rows:
        if synonyms:
            synonym_list = [item.strip() for item in synonyms.split(",") if item.strip()]
            if not synonym_list:
                continue
            best = synonym_list[0]
            score = similarity(headword, best)
            if score < 0.30:
                findings.append(
                    Finding(
                        run_id=run_id,
                        app="words",
                        table_name=source["source_table"],
                        record_id=str(word_id),
                        lesson_id=lesson_id,
                        pattern_id=None,
                        word=best,
                        headword=headword,
                        current_value=synonyms,
                        issue_type="weak_synonym_mapping",
                        severity="high",
                        confidence=0.92,
                        suggested_fix=f"Review synonym list for '{headword}' and replace unrelated lead synonym '{best}'.",
                        explanation=f"Lead synonym '{best}' has low lexical similarity to headword '{headword}'.",
                        evidence=build_rule_evidence(
                            sources=["public.words.synonyms"],
                            similarity_score=score,
                            semantic_relation="synonym",
                            top_alternatives=synonym_list[:3],
                            rule_checks=["lead_synonym_similarity_below_threshold"],
                        ),
                        human_review_required=True,
                    )
                )
        if antonyms:
            antonym_list = [item.strip() for item in antonyms.split(",") if item.strip()]
            if antonym_list and any(item.lower() == headword.lower() for item in antonym_list):
                findings.append(
                    Finding(
                        run_id=run_id,
                        app="words",
                        table_name=source["source_table"],
                        record_id=str(word_id),
                        lesson_id=lesson_id,
                        pattern_id=None,
                        word=antonym_list[0],
                        headword=headword,
                        current_value=antonyms,
                        issue_type="antonym_equals_headword",
                        severity="critical",
                        confidence=0.99,
                        suggested_fix=f"Remove '{headword}' from antonym list and replace it with a true opposite.",
                        explanation="Antonym list contains the headword itself.",
                        evidence=build_rule_evidence(
                            sources=["public.words.antonyms"],
                            semantic_relation="antonym",
                            rule_checks=["antonym_contains_headword"],
                        ),
                        human_review_required=True,
                    )
                )
        if compound_word:
            pieces = tokenize(compound_word)
            if len(pieces) < 2:
                findings.append(
                    Finding(
                        run_id=run_id,
                        app="words",
                        table_name=source["source_table"],
                        record_id=str(word_id),
                        lesson_id=lesson_id,
                        pattern_id=None,
                        word=compound_word,
                        headword=headword,
                        current_value=compound_word,
                        issue_type="compound_word_weak_structure",
                        severity="medium",
                        confidence=0.88,
                        suggested_fix="Review whether the stored compound word is complete and age-appropriate.",
                        explanation="Compound word value does not appear to contain two meaningful components.",
                        evidence=build_rule_evidence(
                            sources=["public.words.compound_word"],
                            rule_checks=["compound_word_component_count_below_2"],
                        ),
                        human_review_required=True,
                    )
                )
        if ambiguity_mode == "skipped_if_no_llm" and not ambiguity_skip_logged:
            coverage.checks_skipped.append("words.ambiguous_headword_detection")
            coverage.skip_reasons.append("LLM not configured for nuanced ambiguity review.")
            ambiguity_skip_logged = True

    return findings
