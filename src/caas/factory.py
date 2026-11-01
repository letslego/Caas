"""Backend selection: SQLite for unit tests, PostgreSQL+pgvector when configured."""
from __future__ import annotations

import os
from typing import Any

from .multiscope import Memory
from .postgres import database_url


def open_memory(url: str | None = None, **kwargs: Any):
    """Return Memory (SQLite) or PostgresMemory based on URL / env."""
    dsn = url if url is not None else database_url()
    if dsn.startswith("postgres"):
        from .pgmemory import PostgresMemory

        return PostgresMemory(dsn, **kwargs)
    # Treat empty / missing as in-memory SQLite; file paths stay SQLite.
    path = dsn or os.getenv("CAAS_SCOPED_DB", ":memory:")
    return Memory(path)
