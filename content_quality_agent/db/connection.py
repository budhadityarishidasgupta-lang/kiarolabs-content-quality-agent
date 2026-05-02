"""Database connection helpers."""

from __future__ import annotations


def connect(db_url: str):
    import psycopg2

    return psycopg2.connect(db_url)
