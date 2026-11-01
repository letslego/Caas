"""PostgreSQL connection, migration, and tenant session helpers."""
from __future__ import annotations

import os
from contextlib import contextmanager
from importlib import resources
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


def database_url(url: str | None = None) -> str:
    return (
        url
        or os.getenv("CAAS_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )


def connect(url: str | None = None) -> psycopg.Connection:
    dsn = database_url(url)
    if not dsn:
        raise RuntimeError("Set CAAS_DATABASE_URL or DATABASE_URL for PostgreSQL")
    conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=False)
    return conn


def schema_sql() -> str:
    return resources.files("caas").joinpath("schema.sql").read_text(encoding="utf-8")


def migrate(url: str | None = None) -> None:
    """Apply the reference schema (idempotent)."""
    with connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql())
        conn.commit()


@contextmanager
def tenant_session(conn: psycopg.Connection, tenant: str) -> Iterator[psycopg.Cursor]:
    """Open a transaction with caas.tenant set for RLS policies."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('caas.tenant', %s, true)", (tenant,))
            yield cur
