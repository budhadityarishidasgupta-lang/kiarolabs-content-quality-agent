"""Schema discovery with explicit reporting and no silent guessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from content_quality_agent.reports.atomic_write import atomic_write_json


@dataclass
class DiscoveryResult:
    spelling_tables: list[str]
    words_tables: list[str]
    words_discovery_confident: bool
    table_columns: dict[str, list[str]]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "spelling_tables": self.spelling_tables,
            "words_tables": self.words_tables,
            "words_discovery_confident": self.words_discovery_confident,
            "table_columns": self.table_columns,
            "notes": self.notes,
        }


def discover_tables(conn, candidate_allowlist: dict, output_path: Path) -> DiscoveryResult:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name ASC
            """
        )
        present = {f"{schema}.{name}" for schema, name in cur.fetchall()}

        cur.execute(
            """
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name ASC, ordinal_position ASC
            """
        )
        raw_columns = cur.fetchall()

    spelling_tables = sorted(
        table for table in present if table.startswith("public.spelling_")
    )

    words_candidates = set(candidate_allowlist.get("words_candidates", []))
    words_tables = sorted(table for table in present if table in words_candidates)

    required_word_markers = {
        "public.courses",
        "public.lessons",
        "public.lesson_words",
        "public.words",
    }
    legacy_word_markers = {
        "public.words_courses",
        "public.words_lessons",
        "public.words_lesson_words",
        "public.words_words",
    }
    words_confident = bool(required_word_markers.issubset(set(words_tables)) or legacy_word_markers.issubset(set(words_tables)))

    notes: list[str] = []
    if not words_confident:
        notes.append("Could not confidently discover the full Words schema from the allowlisted candidate tables.")

    tracked_tables = set(spelling_tables) | set(words_tables)
    table_columns: dict[str, list[str]] = {}
    for schema, table_name, column_name in raw_columns:
        fq_name = f"{schema}.{table_name}"
        if fq_name in tracked_tables:
            table_columns.setdefault(fq_name, []).append(column_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = DiscoveryResult(
        spelling_tables=spelling_tables,
        words_tables=words_tables,
        words_discovery_confident=words_confident,
        table_columns=table_columns,
        notes=notes,
    )
    atomic_write_json(output_path, result.to_dict())
    return result
