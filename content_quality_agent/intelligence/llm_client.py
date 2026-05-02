"""Optional structured LLM client used only for semantic review."""

from __future__ import annotations

from typing import Any


class LLMClient:
    """Very small wrapper so semantic checks can degrade cleanly."""

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def structured_review(self, prompt: str) -> dict[str, Any] | None:
        # Phase 1 keeps LLM optional and non-blocking.
        # We intentionally do not force network dependency for deterministic audits.
        return None
