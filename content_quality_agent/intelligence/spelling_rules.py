"""Config-driven spelling pattern rules with safe defaults."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json


DEFAULT_SPELLING_RULES = {
    "course_pattern_cleanup_scope": {
        "enabled_course_ids": [9],
        "excluded_course_ids": [1],
        "reason": "course_id=9 contains pattern lessons; course_id=1 contains normal spelling sets and must not be pattern-normalized",
    },
    "canonical_patterns": {
        "TION": '"TION" pattern Words',
        "SION": '"SION" pattern Words',
        "SSION": '"SSION" pattern Words',
        "URE": '"URE" pattern Words',
        "PH": '"PH" pattern Words',
        "DGE": '"DGE" pattern Words',
        "FUL/LESS": '"FUL/LESS" pattern Words',
        "SHIP": '"SHIP" pattern Words',
        "HOOD": '"HOOD" pattern Words',
        "CIDE": '"CIDE" pattern Words',
        "OLOGY": '"OLOGY" pattern Words',
        "INESS": '"INESS" pattern Words',
        "ING": '"ING" pattern Words',
        "LY": '"LY" pattern Words',
        "OUS": '"OUS" pattern Words',
        "OUR": '"OUR" pattern Words',
        "OR": '"OR" pattern Words',
        "IC": '"IC" pattern Words',
        "CH": '"CH" pattern Words',
        "GH": '"GH" pattern Words',
        "C": '"C" pattern Words',
        "D/ED": '"D/ED" pattern Words',
        "P'S": '"P\'S" pattern Words',
    },
    "priority_suffix_rules": [
        {"suffix": "ssion", "pattern": "SSION", "confidence": 0.99},
        {"suffix": "tion", "pattern": "TION", "confidence": 0.98},
        {"suffix": "sion", "pattern": "SION", "confidence": 0.96},
        {"suffix": "ship", "pattern": "SHIP", "confidence": 0.98},
        {"suffix": "hood", "pattern": "HOOD", "confidence": 0.98},
        {"suffix": "cide", "pattern": "CIDE", "confidence": 0.98},
        {"suffix": "ology", "pattern": "OLOGY", "confidence": 0.98},
        {"suffix": "iness", "pattern": "INESS", "confidence": 0.98},
        {"suffix": "ure", "pattern": "URE", "confidence": 0.95},
        {"suffix": "ful", "pattern": "FUL/LESS", "confidence": 0.96},
        {"suffix": "less", "pattern": "FUL/LESS", "confidence": 0.96},
    ],
    "contains_rules": [
        {"contains": "dge", "pattern": "DGE", "confidence": 0.97},
        {"contains": "ph", "pattern": "PH", "confidence": 0.93},
        {"contains": "ch", "pattern": "CH", "confidence": 0.91},
        {"contains": "gh", "pattern": "GH", "confidence": 0.90},
    ],
    "hint_clue_rules": [
        {"hint_contains": "cher", "pattern": "URE", "confidence": 0.60, "reason": "pronunciation clue"},
        {"hint_contains": "unstressed", "pattern": "URE", "confidence": 0.60, "reason": "pronunciation clue"},
        {"hint_contains": "life", "pattern": "OLOGY", "confidence": 0.60, "reason": "root meaning clue"},
        {"hint_contains": "silent", "pattern": "GH", "confidence": 0.60, "reason": "silent-letter clue"},
    ],
    "low_confidence_rules": [
        {"suffix": "ing", "pattern": "ING", "confidence": 0.88},
        {"suffix": "ly", "pattern": "LY", "confidence": 0.86},
        {"suffix": "ous", "pattern": "OUS", "confidence": 0.90},
        {"suffix": "our", "pattern": "OUR", "confidence": 0.90},
        {"suffix": "or", "pattern": "OR", "confidence": 0.82},
        {"suffix": "ic", "pattern": "IC", "confidence": 0.82},
        {"suffix": "ed", "pattern": "D/ED", "confidence": 0.78},
        {"contains": "c", "pattern": "C", "confidence": 0.70},
        {"contains": "'", "pattern": "P'S", "confidence": 0.65},
        {"contains": "ps", "pattern": "P'S", "confidence": 0.65},
    ],
}


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
RULES_FILENAME = "spelling_pattern_rules.json"


def _default_rules() -> dict:
    return deepcopy(DEFAULT_SPELLING_RULES)


def _safe_int_list(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    values: list[int] = []
    for item in raw:
        if isinstance(item, int):
            values.append(item)
    return values


def _safe_rule_list(raw: object, *, key: str) -> list[dict]:
    if not isinstance(raw, list):
        return []
    rules: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern", "")).strip().upper()
        confidence = item.get("confidence")
        target = item.get(key)
        if not pattern or not isinstance(confidence, (int, float)) or not isinstance(target, str) or not target.strip():
            continue
        normalized = {key: target.strip().lower(), "pattern": pattern, "confidence": float(confidence)}
        if "reason" in item and isinstance(item["reason"], str):
            normalized["reason"] = item["reason"].strip()
        rules.append(normalized)
    return rules


def _validate_rules(payload: object) -> dict:
    defaults = _default_rules()
    if not isinstance(payload, dict):
        return defaults

    scope = payload.get("course_pattern_cleanup_scope")
    if isinstance(scope, dict):
        defaults["course_pattern_cleanup_scope"] = {
            "enabled_course_ids": _safe_int_list(scope.get("enabled_course_ids")),
            "excluded_course_ids": _safe_int_list(scope.get("excluded_course_ids")),
            "reason": str(scope.get("reason", defaults["course_pattern_cleanup_scope"]["reason"])).strip()
            or defaults["course_pattern_cleanup_scope"]["reason"],
        }

    canonical = payload.get("canonical_patterns")
    if isinstance(canonical, dict):
        safe_canonical = {}
        for key, value in canonical.items():
            if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip():
                safe_canonical[key.strip().upper()] = value.strip()
        if safe_canonical:
            defaults["canonical_patterns"] = safe_canonical

    defaults["priority_suffix_rules"] = _safe_rule_list(payload.get("priority_suffix_rules"), key="suffix") or defaults["priority_suffix_rules"]
    defaults["contains_rules"] = _safe_rule_list(payload.get("contains_rules"), key="contains") or defaults["contains_rules"]
    defaults["hint_clue_rules"] = _safe_rule_list(payload.get("hint_clue_rules"), key="hint_contains") or defaults["hint_clue_rules"]
    defaults["low_confidence_rules"] = _safe_rule_list(payload.get("low_confidence_rules"), key="suffix") + _safe_rule_list(payload.get("low_confidence_rules"), key="contains") or defaults["low_confidence_rules"]
    return defaults


def load_spelling_rules(config_dir: Path | None = None) -> dict:
    resolved_dir = config_dir or CONFIG_DIR
    path = resolved_dir / RULES_FILENAME
    if not path.exists():
        return _default_rules()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_rules()
    return _validate_rules(payload)


def is_course_in_pattern_cleanup_scope(course_id: int, rules: dict) -> bool:
    scope = rules.get("course_pattern_cleanup_scope", {})
    excluded = set(scope.get("excluded_course_ids", []))
    enabled = set(scope.get("enabled_course_ids", []))
    if course_id in excluded:
        return False
    return course_id in enabled


def canonical_lesson_name_for_pattern(pattern: str, rules: dict) -> str:
    normalized = (pattern or "").strip().upper()
    if not normalized:
        return "UNASSIGNED"
    return rules.get("canonical_patterns", {}).get(normalized, "UNASSIGNED")


def get_priority_suffix_rules(rules: dict) -> list[dict]:
    return list(rules.get("priority_suffix_rules", []))


def get_contains_rules(rules: dict) -> list[dict]:
    return list(rules.get("contains_rules", []))


def get_hint_clue_rules(rules: dict) -> list[dict]:
    return list(rules.get("hint_clue_rules", []))


def get_low_confidence_rules(rules: dict) -> list[dict]:
    return list(rules.get("low_confidence_rules", []))
