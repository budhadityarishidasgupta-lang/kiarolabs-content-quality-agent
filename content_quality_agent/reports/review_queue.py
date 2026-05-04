"""Human review queue writer for content-quality findings."""

from __future__ import annotations

import csv
import io


REVIEW_DECISIONS = (
    "approve",
    "reject",
    "defer",
    "false_positive",
    "needs_more_evidence",
)

REVIEW_QUEUE_COLUMNS = [
    "run_id",
    "app",
    "severity",
    "confidence",
    "issue_type",
    "table_name",
    "record_id",
    "lesson_id",
    "pattern_id",
    "word",
    "headword",
    "current_value",
    "suggested_fix",
    "explanation",
    "semantic_relation",
    "similarity_score",
    "relation_evidence",
    "human_decision",
    "approved_value",
    "reviewed_by",
    "reviewed_at",
    "review_notes",
]


def format_review_queue_csv(findings: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_QUEUE_COLUMNS)
    writer.writeheader()
    for finding in findings:
        row = {column: finding.get(column) for column in REVIEW_QUEUE_COLUMNS}
        evidence = finding.get("evidence", {}) or {}
        row["semantic_relation"] = evidence.get("semantic_relation", "")
        row["similarity_score"] = evidence.get("similarity_score", "")
        row["relation_evidence"] = "; ".join(evidence.get("rule_checks", []) or [])
        row["human_decision"] = ""
        row["approved_value"] = ""
        row["reviewed_by"] = ""
        row["reviewed_at"] = ""
        row["review_notes"] = ""
        writer.writerow(row)
    return buffer.getvalue()
