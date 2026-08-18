"""Read-only Maths content integrity checks."""

from __future__ import annotations

import re

from content_quality_agent.models.finding import Evidence, Finding


def _norm(value) -> str:
    return str(value or "").strip()


def _finding(*, run_id: str, record_id, issue_type: str, severity: str, current_value: str, explanation: str, suggested_fix: str, rule_checks: list[str]) -> Finding:
    return Finding(
        run_id=run_id,
        app="math",
        table_name="public.math_questions",
        record_id=str(record_id),
        lesson_id=None,
        pattern_id=None,
        word=None,
        headword=None,
        current_value=current_value,
        issue_type=issue_type,
        severity=severity,
        confidence=1.0,
        suggested_fix=suggested_fix,
        explanation=explanation,
        evidence=Evidence(sources=["public.math_questions"], rule_checks=rule_checks, llm_used=False),
        human_review_required=True,
    )


def audit_math(*, run_id: str, repository, coverage, limit: int | None = None) -> list[Finding]:
    limit_sql = " LIMIT %s" if limit else ""
    params = (limit,) if limit else ()
    rows = repository.query(
        """
        SELECT id, stem, option_a, option_b, option_c, option_d, option_e,
               topic, difficulty, correct_option, COALESCE(hint, ''), COALESCE(explanation, '')
        FROM public.math_questions
        ORDER BY id ASC
        """ + limit_sql,
        params,
    )
    findings: list[Finding] = []
    coverage.records_checked += len(rows)

    seen_fingerprints: dict[str, int] = {}
    for row in rows:
        qid, stem, a, b, c, d, e, topic, difficulty, correct, hint, explanation = row
        stem = _norm(stem)
        options = [_norm(a), _norm(b), _norm(c), _norm(d), _norm(e)]
        labels = ["A", "B", "C", "D", "E"]
        populated = [(label, value) for label, value in zip(labels, options) if value]
        correct_label = _norm(correct).upper()

        if not stem:
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="missing_question_text", severity="critical", current_value="", explanation="Math question has no stem.", suggested_fix="Correct the source CSV and re-ingest this math question.", rule_checks=["stem must be non-empty"]))

        if len(populated) < 2:
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="insufficient_options", severity="critical", current_value=str(options), explanation="Math question has fewer than two populated answer options.", suggested_fix="Correct the source CSV options and re-ingest.", rule_checks=["at least two populated options required"]))

        lowered = [value.lower() for _, value in populated]
        if len(lowered) != len(set(lowered)):
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="duplicate_options", severity="high", current_value=str([v for _, v in populated]), explanation="Math question contains duplicate displayed options.", suggested_fix="Replace duplicate distractors in the source CSV and re-ingest.", rule_checks=["displayed options must be distinct"]))

        option_map = dict(populated)
        if correct_label not in option_map:
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="correct_answer_missing_from_options", severity="critical", current_value=correct_label, explanation="Stored correct_option does not point to a populated displayed option.", suggested_fix="Reconcile the source answer and option set before re-ingestion.", rule_checks=["correct_option must be A-E and point to populated option"]))

        malformed = [value for _, value in populated if re.search(r"[A-Za-z]+\d+$", value)]
        if malformed:
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="malformed_option", severity="high", current_value=str(malformed), explanation="One or more options end with suspicious numeric junk.", suggested_fix="Review the source CSV for extraction/formatting corruption.", rule_checks=["option text should not end in accidental numeric suffixes"]))

        if not _norm(explanation):
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="missing_explanation", severity="medium", current_value="", explanation="Math question has no student-facing explanation.", suggested_fix="Add a worked explanation through the approved content ingestion process.", rule_checks=["student-facing explanation expected"]))

        if not _norm(topic) or not _norm(difficulty):
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="missing_classification", severity="medium", current_value=f"topic={topic!r}; difficulty={difficulty!r}", explanation="Math question is missing topic or difficulty metadata.", suggested_fix="Complete classification in the source CSV and re-ingest.", rule_checks=["topic and difficulty expected"]))

        fingerprint = f"{re.sub(r'\\s+', ' ', stem.lower())}|{option_map.get(correct_label, '').lower()}"
        if stem and fingerprint in seen_fingerprints:
            findings.append(_finding(run_id=run_id, record_id=qid, issue_type="duplicate_question", severity="high", current_value=stem, explanation=f"Question duplicates math question id {seen_fingerprints[fingerprint]} using normalized stem plus correct answer.", suggested_fix="Review whether both records are intentionally distinct; otherwise remove the duplicate through the source CSV workflow.", rule_checks=["normalized stem + correct answer fingerprint must be unique"]))
        elif stem:
            seen_fingerprints[fingerprint] = qid

    return findings
