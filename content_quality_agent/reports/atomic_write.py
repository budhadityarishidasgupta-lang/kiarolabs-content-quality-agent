"""Atomic file writing helpers for report artifacts."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from pathlib import Path


def _atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def atomic_write_text(path: Path, content: str) -> None:
    _atomic_replace(path, content)


def atomic_write_json(path: Path, payload: dict | list) -> None:
    _atomic_replace(path, json.dumps(payload, indent=2))


def atomic_write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field) for field in fieldnames})
    _atomic_replace(path, buffer.getvalue())
