"""Unified context service: Memlayer planes + CaaS durable scopes under NFRs."""
from __future__ import annotations

import json
from typing import Any

from .assemble import assemble_pack
from .episodes import EpisodesMixin
from .knowledge import KnowledgeMixin
from .layers_sql import POSTGRES_LAYERS, SQLITE_LAYERS
from .multiscope import Denied, Principal
from .ops import OpsMixin
from .profile import ProfileMixin
from .working import WorkingMemory


class _SqliteLayers:
    def __init__(self, db):
        self.db = db
        self.db.executescript(SQLITE_LAYERS)

    def execute(self, sql: str, params: tuple = ()):
        # SQLite uses ?
        self.db.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()):
        return self.db.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()):
        return self.db.execute(sql, params).fetchall()

    def commit(self):
        # Memory uses isolation_level=None (autocommit) typically
        try:
            self.db.commit()
        except Exception:
            pass


class _PostgresLayers:
    def __init__(self, conn, tenant_setter=True):
        self.conn = conn
        with self.conn.cursor() as cur:
            cur.execute(POSTGRES_LAYERS)
        self.conn.commit()
        self._tenant = None

    def set_tenant(self, tenant: str):
        self._tenant = tenant

    def execute(self, sql: str, params: tuple = ()):
        pg = sql.replace("?", "%s")
        # SQLite UPSERT uses ON CONFLICT(tenant, subject) — valid in PG too for our DDL
        with self.conn.cursor() as cur:
            if self._tenant:
                cur.execute("SELECT set_config('caas.tenant', %s, true)", (self._tenant,))
            cur.execute(pg, params)

    def fetchone(self, sql: str, params: tuple = ()):
        pg = sql.replace("?", "%s")
        with self.conn.cursor() as cur:
            if self._tenant:
                cur.execute("SELECT set_config('caas.tenant', %s, true)", (self._tenant,))
            cur.execute(pg, params)
            return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()):
        pg = sql.replace("?", "%s")
        with self.conn.cursor() as cur:
            if self._tenant:
                cur.execute("SELECT set_config('caas.tenant', %s, true)", (self._tenant,))
            cur.execute(pg, params)
            return list(cur.fetchall())

    def commit(self):
        self.conn.commit()


class ContextService(OpsMixin, ProfileMixin, EpisodesMixin, KnowledgeMixin):
    """Facade over durable Memory/PostgresMemory + hot/warm planes."""

    def __init__(self, memory, working: WorkingMemory | None = None):
        self.memory = memory
        self.working = working or WorkingMemory()
        if type(memory).__name__ == "PostgresMemory":
            self._layers = _PostgresLayers(memory.conn)
        else:
            self._layers = _SqliteLayers(memory.db)

    # --- SQL bridge for mixins ---
    def _layer_execute(self, sql: str, params: tuple = ()) -> None:
        self._layers.execute(sql, params)

    def _layer_fetchone(self, sql: str, params: tuple = ()):
        return self._layers.fetchone(sql, params)

    def _layer_fetchall(self, sql: str, params: tuple = ()):
        return self._layers.fetchall(sql, params)

    def _layer_commit(self) -> None:
        self._layers.commit()

    def _bind_tenant(self, p: Principal) -> None:
        if hasattr(self._layers, "set_tenant"):
            self._layers.set_tenant(p.tenant)

    # --- Working ---
    def append_turn(
        self, p: Principal, session_id: str, role: str, content: str, **meta: Any
    ):
        self._bind_tenant(p)
        self.assert_writes_allowed(p)
        self.record_usage(p, steps=1)
        return self.working.append(p.tenant, p.subject, session_id, role, content, meta=meta)

    def get_working(self, p: Principal, session_id: str):
        self._bind_tenant(p)
        return self.working.get(p.tenant, p.subject, session_id)

    def clear_working(self, p: Principal, session_id: str) -> None:
        self._bind_tenant(p)
        self.assert_writes_allowed(p)
        self.working.clear(p.tenant, p.subject, session_id)

    # Wrap mixin entrypoints to bind tenant for Postgres RLS
    def set_profile_fact(self, p: Principal, key: str, value: str, *, type_: str = "string"):
        self._bind_tenant(p)
        return ProfileMixin.set_profile_fact(self, p, key, value, type_=type_)

    def get_profile(self, p: Principal, subject: str | None = None):
        self._bind_tenant(p)
        return ProfileMixin.get_profile(self, p, subject)

    def forget_profile_fact(self, p: Principal, key: str):
        self._bind_tenant(p)
        return ProfileMixin.forget_profile_fact(self, p, key)

    def record_episode(self, p: Principal, kind: str, title: str, detail: str = "", **kw):
        self._bind_tenant(p)
        return EpisodesMixin.record_episode(self, p, kind, title, detail, **kw)

    def list_episodes(self, p: Principal, **kw):
        self._bind_tenant(p)
        return EpisodesMixin.list_episodes(self, p, **kw)

    def ingest_document(self, p: Principal, title: str, content: str, source: str, **kw):
        self._bind_tenant(p)
        return KnowledgeMixin.ingest_document(self, p, title, content, source, **kw)

    def search_knowledge(self, p: Principal, query: str, **kw):
        self._bind_tenant(p)
        return KnowledgeMixin.search_knowledge(self, p, query, **kw)

    def set_kill_switch(self, p: Principal, engaged: bool, reason: str = ""):
        self._bind_tenant(p)
        return OpsMixin.set_kill_switch(self, p, engaged, reason)

    def kill_switch_status(self, p: Principal):
        self._bind_tenant(p)
        return OpsMixin.kill_switch_status(self, p)

    def set_caps(
        self,
        p: Principal,
        scope: str = "tenant",
        scope_id: str | None = None,
        max_steps: int | None = None,
        max_spend_micros: int | None = None,
        **kw,
    ):
        self._bind_tenant(p)
        return OpsMixin.set_caps(
            self,
            p,
            scope=scope,
            scope_id=scope_id,
            max_steps=max_steps,
            max_spend_micros=max_spend_micros,
            **kw,
        )

    def get_caps(
        self, p: Principal, scope: str = "tenant", scope_id: str | None = None, **kw
    ):
        self._bind_tenant(p)
        return OpsMixin.get_caps(self, p, scope=scope, scope_id=scope_id, **kw)

    def record_usage(self, p: Principal, **kw):
        self._bind_tenant(p)
        return OpsMixin.record_usage(self, p, **kw)

    def assemble(
        self,
        p: Principal,
        session_id: str,
        query: str,
        scopes: list[tuple[str, str]],
        *,
        max_chars: int = 8000,
        purpose: str = "assistant",
        mode: str = "hybrid",
        include_operational: bool = False,
    ) -> dict[str, Any]:
        self._bind_tenant(p)
        profile = self.get_profile(p)
        kwargs = {"purpose": purpose, "limit": 20, "max_chars": max(500, max_chars // 2)}
        if hasattr(self.memory, "embedder"):
            kwargs["mode"] = mode
        try:
            durable = self.memory.search(p, query, scopes, **kwargs)
        except Denied:
            durable = {"context": "", "items": [], "manifest": []}
        episodes = self.list_episodes(p, limit=10)
        knowledge = self.search_knowledge(p, query, limit=8) if query.strip() else []
        operational = None
        if include_operational:
            operational = {
                "kill": self.kill_switch_status(p),
                "caps": self.get_caps(p).__dict__,
            }
        return assemble_pack(
            p=p,
            session_id=session_id,
            query=query,
            scopes=scopes,
            working=self.working,
            profile=profile,
            durable=durable,
            episodes=episodes,
            knowledge=knowledge,
            max_chars=max_chars,
            include_operational=include_operational,
            operational=operational,
        )


def open_context(url: str | None = None, **kwargs) -> ContextService:
    from .factory import open_memory

    return ContextService(open_memory(url, **kwargs))
