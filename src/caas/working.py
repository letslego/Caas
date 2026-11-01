"""Hot working-memory plane (session turns) with CAS + TTL.

Default backend is in-process. Swap for Redis by implementing WorkingBackend.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Turn:
    id: str
    role: str
    content: str
    at: float
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkingSnapshot:
    tenant: str
    subject: str
    session_id: str
    revision: int
    turns: list[Turn]
    expires_at: float


class WorkingBackend(Protocol):
    def get(self, key: str) -> WorkingSnapshot | None: ...
    def cas(self, key: str, expected: int, snapshot: WorkingSnapshot) -> bool: ...
    def delete(self, key: str) -> None: ...


class InProcessWorkingBackend:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, WorkingSnapshot] = {}

    def get(self, key: str) -> WorkingSnapshot | None:
        with self._lock:
            snap = self._data.get(key)
            if snap is None:
                return None
            if snap.expires_at < time.time():
                self._data.pop(key, None)
                return None
            return snap

    def cas(self, key: str, expected: int, snapshot: WorkingSnapshot) -> bool:
        with self._lock:
            cur = self._data.get(key)
            cur_rev = cur.revision if cur and cur.expires_at >= time.time() else 0
            if cur_rev != expected:
                return False
            self._data[key] = snapshot
            return True

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


def session_key(tenant: str, subject: str, session_id: str) -> str:
    return f"{tenant}:{subject}:{session_id}"


class WorkingMemory:
    def __init__(
        self,
        backend: WorkingBackend | None = None,
        *,
        ttl_sec: int = 3600,
        max_turns: int = 32,
        max_chars: int = 12000,
    ):
        self.backend = backend or InProcessWorkingBackend()
        self.ttl_sec = ttl_sec
        self.max_turns = max_turns
        self.max_chars = max_chars

    def get(self, tenant: str, subject: str, session_id: str) -> WorkingSnapshot:
        key = session_key(tenant, subject, session_id)
        snap = self.backend.get(key)
        if snap is None:
            return WorkingSnapshot(tenant, subject, session_id, 0, [], time.time() + self.ttl_sec)
        return snap

    def append(
        self,
        tenant: str,
        subject: str,
        session_id: str,
        role: str,
        content: str,
        *,
        meta: dict[str, Any] | None = None,
        retries: int = 8,
    ) -> WorkingSnapshot:
        if role not in {"user", "assistant", "tool", "system"}:
            raise ValueError("invalid role")
        if not content.strip():
            raise ValueError("empty content")
        key = session_key(tenant, subject, session_id)
        for _ in range(retries):
            cur = self.get(tenant, subject, session_id)
            turns = list(cur.turns)
            turns.append(
                Turn(uuid.uuid4().hex, role, content, time.time(), meta or {})
            )
            while len(turns) > self.max_turns:
                turns.pop(0)
            # Bound by chars from the end
            total = 0
            kept: list[Turn] = []
            for t in reversed(turns):
                if total + len(t.content) > self.max_chars and kept:
                    break
                kept.append(t)
                total += len(t.content)
            kept.reverse()
            nxt = WorkingSnapshot(
                tenant,
                subject,
                session_id,
                cur.revision + 1,
                kept,
                time.time() + self.ttl_sec,
            )
            if self.backend.cas(key, cur.revision, nxt):
                return nxt
        raise RuntimeError("working memory CAS retries exhausted")

    def clear(self, tenant: str, subject: str, session_id: str) -> None:
        self.backend.delete(session_key(tenant, subject, session_id))
