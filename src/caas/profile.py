"""Profile plane: typed per-user facts with monotonic revision."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .multiscope import Denied, Principal


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


ALLOWED_PROFILE = {
    "language": {"English", "Bengali", "Hindi", "Spanish"},
    "verbosity": {"concise", "balanced", "detailed"},
    "expertise": {"beginner", "intermediate", "advanced"},
    "working_style": {"direct", "collaborative", "socratic"},
    "preferred_role": {"engineering_partner", "analyst", "tutor"},
}


class ProfileMixin:
    def profile_revision(self, p: Principal) -> int:
        row = self._layer_fetchone(
            "SELECT revision FROM profile_revisions WHERE tenant=? AND subject=?",
            (p.tenant, p.subject),
        )
        return int(row["revision"]) if row else 0

    def get_profile(self, p: Principal, subject: str | None = None) -> dict[str, Any]:
        subject = subject or p.subject
        if subject != p.subject:
            raise Denied("profile read denied")
        rows = self._layer_fetchall(
            "SELECT key, type, value, revision, updated_at FROM profile_facts WHERE tenant=? AND subject=?",
            (p.tenant, subject),
        )
        facts = {
            r["key"]: {
                "type": r["type"],
                "value": r["value"],
                "revision": r["revision"],
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        }
        return {"subject": subject, "revision": self.profile_revision(p), "facts": facts}

    def set_profile_fact(
        self, p: Principal, key: str, value: str, *, type_: str = "string"
    ) -> dict[str, Any]:
        self.assert_writes_allowed(p)
        if key in ALLOWED_PROFILE and value not in ALLOWED_PROFILE[key]:
            raise ValueError(f"invalid value for {key}")
        rev = self.profile_revision(p) + 1
        self._layer_execute(
            """INSERT INTO profile_revisions(tenant, subject, revision) VALUES(?,?,?)
               ON CONFLICT(tenant, subject) DO UPDATE SET revision=excluded.revision""",
            (p.tenant, p.subject, rev),
        )
        self._layer_execute(
            """INSERT INTO profile_facts(tenant, subject, key, type, value, revision, updated_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(tenant, subject, key) DO UPDATE SET
                 type=excluded.type, value=excluded.value, revision=excluded.revision,
                 updated_at=excluded.updated_at""",
            (p.tenant, p.subject, key, type_, value, rev, utc()),
        )
        self._layer_commit()
        return self.get_profile(p)

    def forget_profile_fact(self, p: Principal, key: str) -> dict[str, Any]:
        self.assert_writes_allowed(p)
        rev = self.profile_revision(p) + 1
        self._layer_execute(
            """INSERT INTO profile_revisions(tenant, subject, revision) VALUES(?,?,?)
               ON CONFLICT(tenant, subject) DO UPDATE SET revision=excluded.revision""",
            (p.tenant, p.subject, rev),
        )
        self._layer_execute(
            "DELETE FROM profile_facts WHERE tenant=? AND subject=? AND key=?",
            (p.tenant, p.subject, key),
        )
        self._layer_commit()
        return self.get_profile(p)
