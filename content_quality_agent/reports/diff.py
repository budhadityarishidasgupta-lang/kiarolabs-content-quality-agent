"""Diff current findings against the previous latest report."""

from __future__ import annotations


def build_diff(current_findings: list[dict], previous_findings: list[dict] | None) -> dict:
    previous_findings = previous_findings or []
    current_map = {finding["identity_key"]: finding for finding in current_findings}
    previous_map = {finding["identity_key"]: finding for finding in previous_findings}

    return {
        "new_findings": [current_map[key] for key in sorted(set(current_map) - set(previous_map))],
        "persisting_findings": [current_map[key] for key in sorted(set(current_map) & set(previous_map))],
        "resolved_findings": [previous_map[key] for key in sorted(set(previous_map) - set(current_map))],
    }
