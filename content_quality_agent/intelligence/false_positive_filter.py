"""Safe false-positive suppression for known spelling findings."""

from __future__ import annotations

from pathlib import Path
import json


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
ALLOWLIST_FILENAME = "spelling_false_positive_allowlist.json"


def load_false_positive_allowlist(config_dir: Path | None = None) -> dict:
    resolved_dir = config_dir or CONFIG_DIR
    path = resolved_dir / ALLOWLIST_FILENAME
    if not path.exists():
        return {"suppressions": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"suppressions": []}
    suppressions = payload.get("suppressions")
    if not isinstance(suppressions, list):
        return {"suppressions": []}
    safe_rows = []
    for row in suppressions:
        if isinstance(row, dict):
            safe_rows.append(row)
    return {"suppressions": safe_rows}


def _finding_value(finding, field: str):
    if isinstance(finding, dict):
        return finding.get(field)
    return getattr(finding, field, None)


def _matches_text(expected: str, actual: object) -> bool:
    return isinstance(actual, str) and actual.strip().lower() == expected.strip().lower()


def should_suppress_finding(finding, allowlist: dict) -> tuple[bool, str | None]:
    suppressions = allowlist.get("suppressions", [])
    current_value = _finding_value(finding, "current_value")
    lesson_id = _finding_value(finding, "lesson_id")
    word = _finding_value(finding, "word")
    issue_type = _finding_value(finding, "issue_type")

    for rule in suppressions:
        if not isinstance(rule, dict):
            continue
        if "issue_type" in rule and not _matches_text(str(rule["issue_type"]), issue_type):
            continue
        if "word" in rule and not _matches_text(str(rule["word"]), word):
            continue
        if "lesson_id" in rule:
            try:
                if int(rule["lesson_id"]) != int(lesson_id):
                    continue
            except (TypeError, ValueError):
                continue
        if "current_value" in rule and not _matches_text(str(rule["current_value"]), current_value):
            continue
        if "lesson_name" in rule and not _matches_text(str(rule["lesson_name"]), current_value):
            continue
        if "current_value_contains" in rule:
            needle = str(rule["current_value_contains"]).strip().lower()
            if not isinstance(current_value, str) or needle not in current_value.lower():
                continue
        return True, str(rule.get("reason") or "allowlist suppression").strip() or "allowlist suppression"
    return False, None
