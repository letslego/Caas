"""Operational plane: kill switch and step/spend caps."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .multiscope import Denied, Principal


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Caps:
    tenant: str
    scope: str
    scope_id: str
    max_steps: int | None
    max_spend_micros: int | None
    steps: int
    spend_micros: int


class OpsMixin:
    """Expects _layer_execute / _layer_fetchone / _layer_fetchall / _layer_commit helpers."""

    def kill_switch_status(self, p: Principal) -> dict[str, Any]:
        row = self._layer_fetchone(
            "SELECT engaged, reason, updated_at, updated_by FROM kill_switches WHERE tenant=?",
            (p.tenant,),
        )
        if not row:
            return {"engaged": False, "reason": "", "updated_at": None, "updated_by": None}
        engaged = row["engaged"] in (True, 1, "1", "t", "true")
        return {
            "engaged": engaged,
            "reason": row["reason"],
            "updated_at": str(row["updated_at"]),
            "updated_by": row["updated_by"],
        }

    def set_kill_switch(self, p: Principal, engaged: bool, reason: str = "") -> dict[str, Any]:
        # Host/admin operation — caller must authorize outside or be scope admin elsewhere.
        self._layer_execute(
            """INSERT INTO kill_switches(tenant, engaged, reason, updated_at, updated_by)
               VALUES(?,?,?,?,?)
               ON CONFLICT(tenant) DO UPDATE SET
                 engaged=excluded.engaged, reason=excluded.reason,
                 updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
            (p.tenant, 1 if engaged else 0, reason or ("engaged" if engaged else "cleared"), utc(), p.subject),
        )
        self._layer_commit()
        return self.kill_switch_status(p)

    def assert_writes_allowed(self, p: Principal) -> None:
        status = self.kill_switch_status(p)
        if status["engaged"]:
            raise Denied(f"kill switch engaged: {status['reason']}")

    def get_caps(self, p: Principal, scope: str = "tenant", scope_id: str | None = None) -> Caps:
        scope_id = scope_id or p.tenant if scope == "tenant" else scope_id or p.subject
        row = self._layer_fetchone(
            """SELECT tenant, scope, scope_id, max_steps, max_spend_micros, steps, spend_micros
               FROM control_caps WHERE tenant=? AND scope=? AND scope_id=?""",
            (p.tenant, scope, scope_id),
        )
        if not row:
            return Caps(p.tenant, scope, scope_id, None, None, 0, 0)
        return Caps(
            row["tenant"],
            row["scope"],
            row["scope_id"],
            row["max_steps"],
            row["max_spend_micros"],
            int(row["steps"]),
            int(row["spend_micros"]),
        )

    def set_caps(
        self,
        p: Principal,
        *,
        scope: str = "tenant",
        scope_id: str | None = None,
        max_steps: int | None = None,
        max_spend_micros: int | None = None,
    ) -> Caps:
        scope_id = scope_id or (p.tenant if scope == "tenant" else p.subject)
        cur = self.get_caps(p, scope, scope_id)
        self._layer_execute(
            """INSERT INTO control_caps(tenant, scope, scope_id, max_steps, max_spend_micros, steps, spend_micros)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(tenant, scope, scope_id) DO UPDATE SET
                 max_steps=excluded.max_steps, max_spend_micros=excluded.max_spend_micros""",
            (p.tenant, scope, scope_id, max_steps, max_spend_micros, cur.steps, cur.spend_micros),
        )
        self._layer_commit()
        return self.get_caps(p, scope, scope_id)

    def record_usage(
        self,
        p: Principal,
        *,
        steps: int = 1,
        spend_micros: int = 0,
        scope: str = "tenant",
        scope_id: str | None = None,
    ) -> Caps:
        self.assert_writes_allowed(p)
        scope_id = scope_id or (p.tenant if scope == "tenant" else p.subject)
        caps = self.get_caps(p, scope, scope_id)
        new_steps = caps.steps + steps
        new_spend = caps.spend_micros + spend_micros
        if caps.max_steps is not None and new_steps > caps.max_steps:
            raise Denied("step cap exceeded")
        if caps.max_spend_micros is not None and new_spend > caps.max_spend_micros:
            raise Denied("spend cap exceeded")
        self._layer_execute(
            """INSERT INTO control_caps(tenant, scope, scope_id, max_steps, max_spend_micros, steps, spend_micros)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(tenant, scope, scope_id) DO UPDATE SET
                 steps=excluded.steps, spend_micros=excluded.spend_micros""",
            (
                p.tenant,
                scope,
                scope_id,
                caps.max_steps,
                caps.max_spend_micros,
                new_steps,
                new_spend,
            ),
        )
        self._layer_commit()
        return self.get_caps(p, scope, scope_id)
