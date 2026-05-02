"""Confidence threshold helpers."""

from __future__ import annotations


def classify_confidence(score: float, policy: dict) -> str:
    if score >= float(policy["strong_recommendation"]):
        return "strong_recommendation"
    if score >= float(policy["human_review"]):
        return "human_review"
    if score >= float(policy["informational"]):
        return "informational"
    return "ignore"
