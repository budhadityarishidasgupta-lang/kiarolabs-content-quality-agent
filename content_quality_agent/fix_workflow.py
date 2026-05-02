"""Approval-based spelling lesson correction workflow."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from content_quality_agent.db.connection import connect
from content_quality_agent.db.repository import GuardedRepository, RepositoryContext
from content_quality_agent.guardrails import GuardrailEnforcer
from content_quality_agent.intelligence.pattern_detector import (
    canonical_lesson_name_for_pattern,
    detect_spelling_pattern,
    validate_canonical_lesson_name,
)


APPROVED_FIX_COLUMNS = [
    "run_id",
    "app",
    "table_name",
    "record_id",
    "word",
    "current_value",
    "approved_value",
    "fix_type",
    "approved_by",
    "approval_timestamp",
    "reason",
]
ALLOWED_FIX_TYPE = "spelling_lesson_name_correction"
ALLOWED_APPROVED_VALUE_RE = re.compile(r'^"[A-Z0-9/\' -]+" pattern Words$|^UNASSIGNED$')


@dataclass
class FixValidationResult:
    row: dict
    valid: bool
    errors: list[str]
    db_record: dict | None
    approved_value: str | None
    rollback_sql: str | None = None


def generate_spelling_lesson_fix_suggestions(*, config, source_path: Path) -> dict:
    if not config.db_url:
        raise RuntimeError("CONTENT_AUDIT_DB_URL is required for fix generation.")

    rows = _read_csv_rows(source_path)
    candidate_rows = [
        row for row in rows
        if row.get("app") == "spelling"
        and row.get("table_name") == "public.spelling_words"
        and row.get("issue_type") == "pattern_assignment_mismatch"
    ]
    record_ids = sorted({int(row["record_id"]) for row in candidate_rows if str(row.get("record_id", "")).isdigit()})

    conn = connect(config.db_url)
    try:
        repository = GuardedRepository(
            conn,
            GuardrailEnforcer(),
            RepositoryContext("spelling", frozenset({"public.spelling_words"})),
        )
        records = {
            item["record_id"]: item
            for item in repository.fetch_spelling_words_for_fix_candidates(record_ids)
        }
    finally:
        conn.close()

    timestamp = _timestamp()
    fixes_dir = config.reports_dir / "fixes"
    fixes_dir.mkdir(parents=True, exist_ok=True)
    output_path = fixes_dir / f"approved-fixes-template-{timestamp}.csv"

    suggestions: list[dict] = []
    for row in candidate_rows:
        record_id = int(row["record_id"])
        db_record = records.get(record_id)
        if not db_record or db_record["course_id"] != 9:
            continue
        detection = detect_spelling_pattern(
            db_record["word"],
            hint=db_record["hint"],
            current_pattern=db_record["lesson_name"],
        )
        approved_value = detection.canonical_lesson_name
        if approved_value == db_record["lesson_name"]:
            continue
        suggestions.append(
            {
                "run_id": row.get("run_id", ""),
                "app": "spelling",
                "table_name": "public.spelling_words",
                "record_id": str(record_id),
                "word": db_record["word"],
                "current_value": db_record["lesson_name"],
                "approved_value": approved_value,
                "fix_type": ALLOWED_FIX_TYPE,
                "approved_by": "",
                "approval_timestamp": "",
                "reason": "; ".join(detection.evidence) or "detected_canonical_pattern",
            }
        )

    _write_csv(output_path, APPROVED_FIX_COLUMNS, suggestions)
    return {
        "source": str(source_path),
        "output": str(output_path),
        "suggestions": len(suggestions),
    }


def apply_approved_spelling_fixes(*, config, approved_path: Path, dry_run: bool, allow_partial: bool = False) -> dict:
    if not config.db_url:
        raise RuntimeError("CONTENT_AUDIT_DB_URL is required for applying approved fixes.")

    rows = _read_csv_rows(approved_path)
    _ensure_columns(rows, APPROVED_FIX_COLUMNS)

    conn = connect(config.db_url)
    rollback_lines: list[str] = []
    fix_log_rows: list[dict] = []
    try:
        repository = GuardedRepository(
            conn,
            GuardrailEnforcer(phase="phase_2"),
            RepositoryContext("spelling", frozenset({"public.spelling_words"})),
        )
        validation_results = [
            _validate_fix_row(repository, row)
            for row in rows
        ]

        invalid = [result for result in validation_results if not result.valid]
        timestamp = _timestamp()
        fixes_dir = config.reports_dir / "fixes"
        rollback_dir = config.reports_dir / "rollback"
        fixes_dir.mkdir(parents=True, exist_ok=True)
        rollback_dir.mkdir(parents=True, exist_ok=True)

        if invalid and not allow_partial:
            dry_run_report = fixes_dir / f"fix-dry-run-{timestamp}.json"
            dry_run_report.write_text(
                json.dumps(
                    {
                        "source": str(approved_path),
                        "dry_run": dry_run,
                        "valid_rows": len(validation_results) - len(invalid),
                        "invalid_rows": [asdict(item) for item in invalid],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise RuntimeError(f"Approved fixes validation failed for {len(invalid)} row(s). See {dry_run_report}.")

        valid_rows = [result for result in validation_results if result.valid]
        if allow_partial:
            valid_rows = [result for result in validation_results if result.valid]

        for result in valid_rows:
            assert result.db_record is not None
            rollback_sql = _rollback_sql(result.db_record["record_id"], result.db_record["lesson_name"])
            rollback_lines.append(rollback_sql)
            fix_log_rows.append(
                {
                    "record_id": result.db_record["record_id"],
                    "word": result.db_record["word"],
                    "old_lesson_name": result.db_record["lesson_name"],
                    "new_lesson_name": result.approved_value,
                    "approved_by": result.row["approved_by"],
                    "applied_at": datetime.now(timezone.utc).isoformat(),
                    "rollback_sql": rollback_sql,
                }
            )

        rollback_path = rollback_dir / f"rollback-{timestamp}.sql"
        rollback_path.write_text("\n".join(rollback_lines) + ("\n" if rollback_lines else ""), encoding="utf-8")

        dry_run_report = fixes_dir / f"fix-dry-run-{timestamp}.json"
        if dry_run:
            dry_run_report.write_text(
                json.dumps(
                    {
                        "source": str(approved_path),
                        "dry_run": True,
                        "would_apply": len(valid_rows),
                        "skipped_invalid": len(invalid),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            for result in valid_rows:
                assert result.db_record is not None and result.approved_value is not None
                rowcount = repository.execute_update(
                    """
                    UPDATE public.spelling_words
                    SET lesson_name = %s
                    WHERE word_id = %s
                      AND course_id = 9
                      AND lesson_name = %s
                    """,
                    (
                        result.approved_value,
                        result.db_record["record_id"],
                        result.db_record["lesson_name"],
                    ),
                )
                if rowcount != 1:
                    conn.rollback()
                    raise RuntimeError(f"Failed to apply approved fix for record {result.db_record['record_id']}.")
            conn.commit()

        log_json_path = fixes_dir / f"fix-log-{timestamp}.json"
        log_csv_path = fixes_dir / f"fix-log-{timestamp}.csv"
        log_json_path.write_text(json.dumps(fix_log_rows, indent=2), encoding="utf-8")
        _write_csv(
            log_csv_path,
            ["record_id", "word", "old_lesson_name", "new_lesson_name", "approved_by", "applied_at", "rollback_sql"],
            fix_log_rows,
        )

        return {
            "source": str(approved_path),
            "dry_run": dry_run,
            "applied": 0 if dry_run else len(valid_rows),
            "validated": len(valid_rows),
            "skipped_invalid": len(invalid),
            "rollback_sql": str(rollback_path),
            "log_json": str(log_json_path),
            "log_csv": str(log_csv_path),
            "dry_run_report": str(dry_run_report),
        }
    finally:
        conn.close()


def _validate_fix_row(repository: GuardedRepository, row: dict) -> FixValidationResult:
    errors: list[str] = []
    approved_value = (row.get("approved_value") or "").strip()
    record_id_raw = (row.get("record_id") or "").strip()

    if row.get("app") != "spelling":
        errors.append("app must be spelling")
    if row.get("table_name") != "public.spelling_words":
        errors.append("table_name must be public.spelling_words")
    if row.get("fix_type") != ALLOWED_FIX_TYPE:
        errors.append(f"fix_type must be {ALLOWED_FIX_TYPE}")
    if not record_id_raw.isdigit():
        errors.append("record_id must be numeric")
        return FixValidationResult(row=row, valid=False, errors=errors, db_record=None, approved_value=None)

    if not approved_value or not ALLOWED_APPROVED_VALUE_RE.match(approved_value) or not validate_canonical_lesson_name(approved_value):
        errors.append("approved_value must be canonical or UNASSIGNED")
    if not (row.get("approved_by") or "").strip():
        errors.append("approved_by must not be empty")
    if not (row.get("approval_timestamp") or "").strip():
        errors.append("approval_timestamp must not be empty")

    record_id = int(record_id_raw)
    db_record = repository.fetch_spelling_word_for_update(record_id)
    if not db_record:
        errors.append("record_id does not exist")
        return FixValidationResult(row=row, valid=False, errors=errors, db_record=None, approved_value=approved_value or None)

    if db_record["course_id"] != 9:
        errors.append("course_id must be 9")
    if db_record["lesson_name"] != (row.get("current_value") or ""):
        errors.append("current DB value does not match current_value")

    rollback_sql = _rollback_sql(record_id, db_record["lesson_name"])
    return FixValidationResult(
        row=row,
        valid=not errors,
        errors=errors,
        db_record=db_record,
        approved_value=approved_value,
        rollback_sql=rollback_sql,
    )


def _ensure_columns(rows: list[dict], columns: list[str]) -> None:
    if not rows:
        return
    missing = [column for column in columns if column not in rows[0]]
    if missing:
        raise RuntimeError(f"Missing required columns: {', '.join(missing)}")


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _rollback_sql(record_id: int, old_value: str) -> str:
    escaped = old_value.replace("'", "''")
    return f"UPDATE public.spelling_words SET lesson_name = '{escaped}' WHERE word_id = {record_id} AND course_id = 9;"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
