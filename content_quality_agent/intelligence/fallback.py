"""LLM fallback decisions."""

from __future__ import annotations


def fallback_mode(policy: dict, check_name: str) -> str:
    return str(policy.get(check_name, "degraded"))


def semantic_checks_partial(policy: dict, llm_available: bool) -> bool:
    if llm_available:
        return False
    return any(mode in {"degraded", "skipped_if_no_llm"} for mode in policy.values())
