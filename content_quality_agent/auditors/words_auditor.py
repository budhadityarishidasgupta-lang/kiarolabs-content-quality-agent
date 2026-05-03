"""Words content quality auditor."""

from __future__ import annotations

from pathlib import Path
import json

from content_quality_agent.intelligence.fallback import fallback_mode
from content_quality_agent.intelligence.semantic_evidence import build_rule_evidence, similarity, tokenize
from content_quality_agent.intelligence.semantic_relation import classify_candidate_relation
from content_quality_agent.intelligence.words_schema_classifier import classify_words_schema
from content_quality_agent.models.finding import Finding


DEFAULT_WORDS_AUDIT_POLICY = {
    "max_mixed_content_findings": 25,
    "emit_candidate_relation_evidence": True,
    "weak_synonym_requires_relation_confidence": 0.80,
    "mixed_content_unclear_severity": "medium",
    "schema_unclear_should_not_collapse_score": True,
}


def _resolve_words_source(schema_summary: dict) -> dict | None:
    table_columns = schema_summary.get("table_columns", {})

    public_words = set(table_columns.get("public.words", []))
    if {"word_id", "headword", "synonyms"}.issubset(public_words):
        option_columns = sorted(
            column for column in public_words
            if any(token in column.lower() for token in ("option", "choice", "distractor", "answer_"))
        )
        return {
            "source_table": "public.words",
            "id_column": "word_id",
            "headword_column": "headword",
            "synonym_column": "synonyms",
            "correct_answer_column": "correct_answer" if "correct_answer" in public_words else None,
            "option_columns": option_columns,
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
        option_columns = sorted(
            column for column in legacy_words
            if any(token in column.lower() for token in ("option", "choice", "distractor", "answer_"))
        )
        return {
            "source_table": "public.words_words",
            "id_column": "id",
            "headword_column": "word",
            "synonym_column": "correct_answer",
            "correct_answer_column": "correct_answer",
            "option_columns": option_columns,
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


def _load_words_audit_policy() -> dict:
    config_path = Path(__file__).resolve().parents[2] / "config" / "words_audit_policy.json"
    if not config_path.exists():
        return dict(DEFAULT_WORDS_AUDIT_POLICY)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_WORDS_AUDIT_POLICY)
    policy = dict(DEFAULT_WORDS_AUDIT_POLICY)
    if isinstance(payload, dict):
        policy.update({key: value for key, value in payload.items() if key in policy})
    return policy


def _sample_rows_for_classification(rows: list[tuple]) -> list[dict]:
    sample = []
    for row in rows[:50]:
        sample.append(
            {
                "record_id": row[0],
                "headword": row[1],
                "synonyms": row[2],
                "lesson_id": row[5] if len(row) > 5 else None,
            }
        )
    return sample


def _relation_rule_checks(relation_result, *, emit_candidate_relation_evidence: bool) -> list[str]:
    return list(relation_result.evidence) if emit_candidate_relation_evidence else []


def _mixed_content_findings(*, run_id: str, source: dict, rows: list[tuple], classification, policy: dict, coverage) -> list[Finding]:
    findings: list[Finding] = []
    max_findings = int(policy.get("max_mixed_content_findings", 25) or 25)
    emitted = 0

    for word_id, headword, synonyms, _antonyms, _compound_word, lesson_id in rows:
        if emitted >= max_findings:
            break
        candidates = [item.strip() for item in (synonyms or "").split(",") if item.strip()]
        relation_checks: list[str] = []
        for candidate in candidates[:3]:
            relation = classify_candidate_relation(headword, candidate)
            if relation.relation == "likely_antonym":
                relation_checks.extend(relation.evidence)
        findings.append(
            Finding(
                run_id=run_id,
                app="words",
                table_name=source["source_table"],
                record_id=str(word_id),
                lesson_id=lesson_id,
                pattern_id=None,
                word=candidates[0] if candidates else None,
                headword=headword,
                current_value=synonyms,
                issue_type="possible_distractor_column_misread_as_synonym_list" if relation_checks else "words_content_shape_unclear",
                severity=str(policy.get("mixed_content_unclear_severity", "medium")),
                confidence=0.72 if relation_checks else 0.68,
                suggested_fix="Review the Words content shape before treating option lists as synonym lists.",
                explanation="Words content appears to mix headwords with distractor-style answer options, so row-level synonym findings were capped.",
                evidence=build_rule_evidence(
                    sources=[f"{source['source_table']}.{source['synonym_column']}"],
                    semantic_relation="unknown",
                    top_alternatives=candidates[:3],
                    rule_checks=["words_content_shape_mixed_or_unclear", *classification.evidence, *relation_checks],
                ),
                human_review_required=True,
            )
        )
        emitted += 1

    capped = max(0, len(rows) - emitted)
    coverage.capped_findings += capped
    if capped:
        coverage.notes.append(f"Capped {capped} additional Words mixed-content findings.")
    return findings


def audit_words(*, run_id: str, repository, coverage, confidence_policy: dict, llm_fallback_policy: dict, schema_summary: dict, limit: int | None = None) -> list[Finding]:
    findings: list[Finding] = []
    policy = _load_words_audit_policy()
    coverage.schema_unclear_should_not_collapse_score = bool(policy.get("schema_unclear_should_not_collapse_score"))

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

    classification = classify_words_schema(
        schema_summary,
        _sample_rows_for_classification(rows),
        preferred_source_table=source["source_table"],
    )
    coverage.words_schema_classification = classification.classification
    coverage.words_schema_confidence = classification.confidence
    coverage.notes.append(f"Words schema classification: {classification.classification}")
    coverage.notes.append(f"Words schema confidence: {classification.confidence:.2f}")
    for note in classification.warning_notes:
        coverage.notes.append(note)
    if classification.classification == "mixed_content_unknown":
        coverage.words_audit_partial = True
        coverage.notes.append("Words audit is partial due to mixed content shape.")

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
    if ambiguity_mode == "skipped_if_no_llm":
        coverage.checks_skipped.append("words.ambiguous_headword_detection")
        coverage.skip_reasons.append("LLM not configured for nuanced ambiguity review.")

    if classification.classification == "unsupported_schema":
        coverage.records_skipped += len(rows)
        return [
            Finding(
                run_id=run_id,
                app="words",
                table_name="schema.discovery",
                record_id="words-unsupported",
                lesson_id=None,
                pattern_id=None,
                word=None,
                headword=None,
                current_value="words_schema_unsupported",
                issue_type="schema_discovery_failed",
                severity="critical",
                confidence=1.0,
                suggested_fix="Confirm the live Words schema and update the source mapping before rerunning the Words audit.",
                explanation="Words schema could not be safely classified for auditing.",
                evidence=build_rule_evidence(
                    sources=list((schema_summary.get("table_columns") or {}).keys()),
                    rule_checks=["words_schema_unsupported", *classification.evidence],
                ),
                human_review_required=True,
            )
        ]

    if classification.classification == "mixed_content_unknown":
        return _mixed_content_findings(
            run_id=run_id,
            source=source,
            rows=rows,
            classification=classification,
            policy=policy,
            coverage=coverage,
        )

    for word_id, headword, synonyms, antonyms, compound_word, lesson_id in rows:
        if classification.classification == "multiple_choice_options":
            option_candidates = [item.strip() for item in (synonyms or "").split(",") if item.strip()]
            if option_candidates:
                relation_results = [classify_candidate_relation(headword, candidate) for candidate in option_candidates]
                threshold = float(policy.get("weak_synonym_requires_relation_confidence", 0.8))
                if not any(result.relation == "likely_synonym" and result.confidence >= threshold for result in relation_results):
                    best_relation = relation_results[0]
                    findings.append(
                        Finding(
                            run_id=run_id,
                            app="words",
                            table_name=source["source_table"],
                            record_id=str(word_id),
                            lesson_id=lesson_id,
                            pattern_id=None,
                            word=option_candidates[0],
                            headword=headword,
                            current_value=synonyms,
                            issue_type="option_quality_warning",
                            severity="medium",
                            confidence=0.8,
                            suggested_fix=f"Review answer option quality for '{headword}' and ensure a clear synonym is present.",
                            explanation="No likely correct synonym was detected among the available Words options.",
                            evidence=build_rule_evidence(
                                sources=[f"{source['source_table']}.{source['synonym_column']}"],
                                semantic_relation=best_relation.relation,
                                top_alternatives=option_candidates[:3],
                                rule_checks=["multiple_choice_options_without_clear_synonym", *classification.evidence, *_relation_rule_checks(best_relation, emit_candidate_relation_evidence=bool(policy.get('emit_candidate_relation_evidence')))],
                            ),
                            human_review_required=True,
                        )
                    )
        elif synonyms:
            synonym_list = [item.strip() for item in synonyms.split(",") if item.strip()]
            if synonym_list:
                best = synonym_list[0]
                score = similarity(headword, best)
                relation = classify_candidate_relation(headword, best)
                threshold = float(policy.get("weak_synonym_requires_relation_confidence", 0.8))
                if relation.relation == "likely_antonym" and relation.confidence >= threshold:
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
                            confidence=max(0.85, relation.confidence),
                            suggested_fix=f"Review synonym list for '{headword}' and replace unrelated lead synonym '{best}'.",
                            explanation=f"Lead synonym '{best}' is strongly classified as likely antonym for headword '{headword}'.",
                            evidence=build_rule_evidence(
                                sources=[f"{source['source_table']}.{source['synonym_column']}"],
                                similarity_score=score,
                                semantic_relation=relation.relation,
                                top_alternatives=synonym_list[:3],
                                rule_checks=["lead_synonym_relation_failed", *classification.evidence, *_relation_rule_checks(relation, emit_candidate_relation_evidence=bool(policy.get('emit_candidate_relation_evidence')))],
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
                            sources=[f"{source['source_table']}.{source['antonym_column']}"],
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
                            sources=[f"{source['source_table']}.{source['compound_column']}"],
                            rule_checks=["compound_word_component_count_below_2"],
                        ),
                        human_review_required=True,
                    )
                )

    return findings
