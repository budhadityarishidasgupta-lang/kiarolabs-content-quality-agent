"""Read-only Verbal Reasoning content integrity checks."""

from __future__ import annotations

import re

from content_quality_agent.models.finding import Evidence, Finding


def _norm(value) -> str:
    return str(value or "").strip()


def _finding(*, run_id: str, record_id, paper_code: str, issue_type: str, severity: str, current_value: str, explanation: str, suggested_fix: str, rule_checks: list[str]) -> Finding:
    return Finding(
        run_id=run_id,
        app="vr",
        table_name="public.vr_questions/public.vr_answers",
        record_id=str(record_id),
        lesson_id=None,
        pattern_id=None,
        word=None,
        headword=paper_code,
        current_value=current_value,
        issue_type=issue_type,
        severity=severity,
        confidence=1.0,
        suggested_fix=suggested_fix,
        explanation=explanation,
        evidence=Evidence(sources=["public.vr_questions", "public.vr_answers"], rule_checks=rule_checks, llm_used=False),
        human_review_required=True,
    )


def audit_vr(*, run_id: str, repository, coverage, limit: int | None = None) -> list[Finding]:
    limit_sql = " LIMIT %s" if limit else ""
    params = (limit,) if limit else ()
    rows = repository.query(
        """
        SELECT q.id, q.paper_code, q.question_number, q.question_type, q.question_text,
               q.option_a, q.option_b, q.option_c, q.option_d, q.option_e,
               a.correct_answer, COALESCE(a.explanation, ''), COALESCE(a.answer_source, '')
        FROM public.vr_questions q
        LEFT JOIN public.vr_answers a
          ON a.paper_code = q.paper_code AND a.question_number = q.question_number
        ORDER BY q.paper_code ASC, q.question_number ASC
        """ + limit_sql,
        params,
    )
    findings: list[Finding] = []
    coverage.records_checked += len(rows)
    seen_fingerprints: dict[str, tuple[str, int]] = {}

    for row in rows:
        qid, paper, qnum, qtype, text, a, b, c, d, e, correct, explanation, answer_source = row
        text = _norm(text)
        options = [_norm(a), _norm(b), _norm(c), _norm(d), _norm(e)]
        labels = ["A", "B", "C", "D", "E"]
        populated = [(label, value) for label, value in zip(labels, options) if value]
        correct_label = _norm(correct).upper()
        option_map = dict(populated)

        if not text or text.lower() == f"question {qnum}".lower():
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="missing_or_placeholder_question", severity="critical", current_value=text, explanation="VR question text is blank or a placeholder rather than a real question.", suggested_fix="Reconcile the original question source and re-ingest via the VR CSV/admin workflow.", rule_checks=["question_text must contain the real question"] ))

        if not correct_label:
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="missing_answer", severity="critical", current_value="", explanation="VR question has no matching answer row.", suggested_fix="Reconcile against the matching answer source before publishing the paper.", rule_checks=["every question requires a matching vr_answers row"]))
        elif correct_label not in option_map:
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="answer_not_in_options", severity="critical", current_value=correct_label, explanation="The answer key points to an option that is not populated.", suggested_fix="Reconcile question options and answer key from source material before re-ingestion.", rule_checks=["correct_answer must reference a populated A-E option"]))

        lowered = [value.lower() for _, value in populated]
        if len(lowered) != len(set(lowered)):
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="duplicate_options", severity="high", current_value=str([v for _, v in populated]), explanation="VR question contains duplicate answer options.", suggested_fix="Correct distractors in the source CSV and re-ingest.", rule_checks=["displayed options must be distinct"]))

        malformed = [value for _, value in populated if re.search(r"[A-Za-z]+\d+$", value)]
        if malformed:
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="malformed_option", severity="high", current_value=str(malformed), explanation="One or more VR options contain a suspicious trailing numeric suffix.", suggested_fix="Review source extraction and correct via CSV ingestion.", rule_checks=["option formatting integrity"]))

        if not _norm(explanation):
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="missing_explanation", severity="high", current_value="", explanation="VR question has no student-facing explanation.", suggested_fix="Add an independently checked explanation to the approved answer CSV and re-ingest.", rule_checks=["explanation required for post-test learning feedback"]))

        if not _norm(qtype):
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="missing_question_type", severity="medium", current_value="", explanation="VR question is missing question_type classification.", suggested_fix="Classify the item in the source CSV before re-ingestion.", rule_checks=["question_type expected"]))

        fingerprint = f"{re.sub(r'\\s+', ' ', text.lower())}|{option_map.get(correct_label, '').lower()}"
        if text and fingerprint in seen_fingerprints:
            prior_paper, prior_qnum = seen_fingerprints[fingerprint]
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="duplicate_question", severity="high", current_value=text, explanation=f"Question duplicates {prior_paper} question {prior_qnum} using normalized question + correct-answer fingerprint.", suggested_fix="Review the source bank and remove unintended duplication through CSV ingestion.", rule_checks=["global VR question fingerprint should be unique"]))
        elif text:
            seen_fingerprints[fingerprint] = (paper, qnum)

        if correct_label and not _norm(answer_source):
            findings.append(_finding(run_id=run_id, record_id=qid, paper_code=paper, issue_type="missing_answer_source", severity="medium", current_value="", explanation="VR answer has no source provenance marker.", suggested_fix="Ensure answer_source is populated during approved ingestion.", rule_checks=["answer provenance expected"]))

    return findings
