"""Repository layer with mandatory guardrail enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from content_quality_agent.guardrails import GuardrailContext, GuardrailEnforcer


@dataclass
class RepositoryContext:
    app: str
    allowed_tables: frozenset[str]


class GuardedRepository:
    """Single read-only repository abstraction for all DB access."""

    def __init__(self, conn, guardrails: GuardrailEnforcer, context: RepositoryContext) -> None:
        self.conn = conn
        self.guardrails = guardrails
        self.context = context

    def query(self, sql: str, params: tuple | None = None) -> list[tuple]:
        self.guardrails.validate(
            sql,
            GuardrailContext(app=self.context.app, allowed_tables=self.context.allowed_tables),
        )
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()

    def query_one(self, sql: str, params: tuple | None = None):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute_update(self, sql: str, params: tuple | None = None) -> int:
        self.guardrails.validate_mutation(
            sql,
            GuardrailContext(app=self.context.app, allowed_tables=self.context.allowed_tables),
        )
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount

    def fetch_spelling_words_for_fix_candidates(self, record_ids: list[int]) -> list[dict]:
        if not record_ids:
            return []
        rows = self.query(
            """
            SELECT
                word_id,
                course_id,
                word,
                COALESCE(hint, ''),
                COALESCE(lesson_name, '')
            FROM public.spelling_words
            WHERE word_id = ANY(%s)
            ORDER BY word_id ASC
            """,
            (record_ids,),
        )
        return [
            {
                "record_id": row[0],
                "course_id": row[1],
                "word": row[2],
                "hint": row[3],
                "lesson_name": row[4],
            }
            for row in rows
        ]

    def fetch_spelling_word_for_update(self, record_id: int) -> dict | None:
        row = self.query_one(
            """
            SELECT
                word_id,
                course_id,
                word,
                COALESCE(hint, ''),
                COALESCE(lesson_name, '')
            FROM public.spelling_words
            WHERE word_id = %s
            """,
            (record_id,),
        )
        if not row:
            return None
        return {
            "record_id": row[0],
            "course_id": row[1],
            "word": row[2],
            "hint": row[3],
            "lesson_name": row[4],
        }
