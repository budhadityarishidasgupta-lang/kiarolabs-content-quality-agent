"""Configuration loading for the content quality agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"


class ConfigError(RuntimeError):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class RuntimeConfig:
    db_url: str | None
    openai_api_key: str | None
    reports_dir: Path
    fail_on: tuple[str, ...]
    audit_config: dict
    table_allowlist: dict
    confidence_policy: dict
    llm_fallback_policy: dict


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_runtime_config(reports_dir_override: str | None = None) -> RuntimeConfig:
    _load_dotenv(ROOT_DIR / ".env")

    reports_dir = Path(
        reports_dir_override
        or os.getenv("CONTENT_AUDIT_REPORTS_DIR")
        or "reports"
    )
    if not reports_dir.is_absolute():
        reports_dir = ROOT_DIR / reports_dir

    fail_on = tuple(
        item.strip().lower()
        for item in (os.getenv("CONTENT_AUDIT_FAIL_ON") or "critical,high").split(",")
        if item.strip()
    )

    return RuntimeConfig(
        db_url=os.getenv("CONTENT_AUDIT_DB_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        reports_dir=reports_dir,
        fail_on=fail_on,
        audit_config=_load_json(CONFIG_DIR / "audit_config.example.json"),
        table_allowlist=_load_json(CONFIG_DIR / "table_allowlist.example.json"),
        confidence_policy=_load_json(CONFIG_DIR / "confidence_policy.json"),
        llm_fallback_policy=_load_json(CONFIG_DIR / "llm_fallback_policy.json"),
    )
