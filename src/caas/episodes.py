"""Episodic plane: durable timestamped events."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .multiscope import Principal


def utc() -> datetime:
    return datetime.now(timezone.utc)


class EpisodesMixin:
    def record_episode(
        self,
        p: Principal,
        kind: str,
        title: str,
        detail: str = "",
        *,
        attrs: dict[str, Any] | None = None,
        subject: str | None = None,
    ) -> dict[str, Any]:
        self.assert_writes_allowed(p)
        subject = subject or p.subject
        if subject != p.subject:
            # Only self for reference; hosts can extend later.
            from .multiscope import Denied

            raise Denied("episode subject mismatch")
        eid = uuid.uuid4().hex
        at = utc()
        self._layer_execute(
            """INSERT INTO episodes(id, tenant, subject, kind, title, detail, at, attrs)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                eid,
                p.tenant,
                subject,
                kind,
                title,
                detail,
                at.isoformat(),
                json.dumps(attrs or {}),
            ),
        )
        self._layer_commit()
        return {
            "id": eid,
            "tenant": p.tenant,
            "subject": subject,
            "kind": kind,
            "title": title,
            "detail": detail,
            "at": at.isoformat(),
            "attrs": attrs or {},
        }

    def list_episodes(
        self, p: Principal, *, limit: int = 20, subject: str | None = None
    ) -> list[dict[str, Any]]:
        subject = subject or p.subject
        if subject != p.subject:
            from .multiscope import Denied

            raise Denied("episode list denied")
        if not 1 <= limit <= 100:
            raise ValueError("limit out of range")
        rows = self._layer_fetchall(
            """SELECT id, tenant, subject, kind, title, detail, at, attrs
               FROM episodes WHERE tenant=? AND subject=?
               ORDER BY at DESC LIMIT ?""",
            (p.tenant, subject, limit),
        )
        out = []
        for r in rows:
            attrs = r["attrs"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            out.append(
                {
                    "id": r["id"],
                    "tenant": r["tenant"],
                    "subject": r["subject"],
                    "kind": r["kind"],
                    "title": r["title"],
                    "detail": r["detail"],
                    "at": str(r["at"]),
                    "attrs": attrs or {},
                }
            )
        return out
