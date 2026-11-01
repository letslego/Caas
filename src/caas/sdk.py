"""Python SDK client for the CaaS multi-scope HTTP API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence

import httpx


class CaasError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"CaaS HTTP {status}: {detail}")


class CaasClient:
    """Thin HTTP client. Identity is sent via verified-dev headers or a bearer token."""

    def __init__(
        self,
        base_url: str,
        *,
        tenant: str,
        subject: str,
        groups: Iterable[str] = (),
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.tenant = tenant
        self.subject = subject
        self.groups = list(groups)
        self.token = token
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "CaasClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-Verified-Tenant": self.tenant,
            "X-Verified-Subject": self.subject,
            "X-Verified-Groups": ",".join(self.groups),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(
            method,
            self.base_url + path,
            headers=self._headers(),
            **kwargs,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise CaasError(resp.status_code, detail)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # --- scopes / grants / memory -------------------------------------------

    def create_scope(self, kind: str, scope_id: str, classification: str = "internal") -> dict:
        return self._request(
            "POST",
            "/v1/scopes",
            json={"kind": kind, "scope_id": scope_id, "classification": classification},
        )

    def grant(self, kind: str, scope_id: str, subject: str, permission: str) -> dict:
        return self._request(
            "POST",
            "/v1/grants",
            json={
                "kind": kind,
                "scope_id": scope_id,
                "subject": subject,
                "permission": permission,
            },
        )

    def revoke(self, kind: str, scope_id: str, subject: str, permission: str) -> dict:
        return self._request(
            "DELETE",
            "/v1/grants",
            json={
                "kind": kind,
                "scope_id": scope_id,
                "subject": subject,
                "permission": permission,
            },
        )

    def write_memory(
        self,
        kind: str,
        scope_id: str,
        content: str,
        source: str,
        *,
        memory_type: str = "fact",
        classification: str = "internal",
        purpose: str = "assistant",
    ) -> dict:
        return self._request(
            "POST",
            "/v1/memories",
            json={
                "kind": kind,
                "scope_id": scope_id,
                "content": content,
                "source": source,
                "memory_type": memory_type,
                "classification": classification,
                "purpose": purpose,
            },
        )

    def get_memory(self, mid: str) -> dict:
        return self._request("GET", f"/v1/memories/{mid}")

    def revise_memory(
        self, mid: str, content: str, expected_version: int, *, delete: bool = False
    ) -> dict | None:
        return self._request(
            "PATCH",
            f"/v1/memories/{mid}",
            json={
                "content": content,
                "expected_version": expected_version,
                "delete": delete,
            },
        )

    def promote_memory(
        self, mid: str, target_kind: str, target_id: str, purpose: str = "assistant"
    ) -> dict:
        return self._request(
            "POST",
            f"/v1/memories/{mid}/promote",
            json={
                "target_kind": target_kind,
                "target_id": target_id,
                "purpose": purpose,
            },
        )

    def retrieve(
        self,
        query: str,
        scopes: Sequence[tuple[str, str]],
        *,
        purpose: str = "assistant",
        limit: int = 20,
        max_chars: int = 6000,
        mode: str = "hybrid",
    ) -> dict:
        return self._request(
            "POST",
            "/v1/context:retrieve",
            json={
                "query": query,
                "scopes": [list(s) for s in scopes],
                "purpose": purpose,
                "limit": limit,
                "max_chars": max_chars,
                "mode": mode,
            },
        )

    # --- temporal graph -----------------------------------------------------

    def upsert_node(
        self,
        label: str,
        kind: str = "entity",
        attrs: dict | None = None,
        memory_id: str | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/v1/graph/nodes",
            json={
                "label": label,
                "kind": kind,
                "attrs": attrs or {},
                "memory_id": memory_id,
            },
        )

    def get_node(self, node_id: str, at: datetime | None = None) -> dict:
        params = {}
        if at is not None:
            params["at"] = at.isoformat()
        return self._request("GET", f"/v1/graph/nodes/{node_id}", params=params)

    def close_node(self, node_id: str) -> dict:
        return self._request("DELETE", f"/v1/graph/nodes/{node_id}")

    def relate(
        self,
        src_label: str,
        relation: str,
        dst_label: str,
        *,
        src_kind: str = "entity",
        dst_kind: str = "entity",
        attrs: dict | None = None,
        memory_id: str | None = None,
        replace: bool = True,
    ) -> dict:
        return self._request(
            "POST",
            "/v1/graph/relate",
            json={
                "src_label": src_label,
                "relation": relation,
                "dst_label": dst_label,
                "src_kind": src_kind,
                "dst_kind": dst_kind,
                "attrs": attrs or {},
                "memory_id": memory_id,
                "replace": replace,
            },
        )

    def unrelate(self, **kwargs: Any) -> dict:
        return self._request("POST", "/v1/graph/unrelate", json=kwargs)

    def neighbors(
        self,
        label: str,
        *,
        relation: str | None = None,
        direction: str = "both",
        kind: str = "entity",
        at: datetime | None = None,
        limit: int = 50,
    ) -> list:
        return self._request(
            "POST",
            "/v1/graph/neighbors",
            json={
                "label": label,
                "relation": relation,
                "direction": direction,
                "kind": kind,
                "at": at.isoformat() if at else None,
                "limit": limit,
            },
        )

    def path(
        self,
        src_label: str,
        dst_label: str,
        *,
        max_hops: int = 3,
        relation: str | None = None,
        src_kind: str = "entity",
        dst_kind: str = "entity",
        at: datetime | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/v1/graph/path",
            json={
                "src_label": src_label,
                "dst_label": dst_label,
                "max_hops": max_hops,
                "relation": relation,
                "src_kind": src_kind,
                "dst_kind": dst_kind,
                "at": at.isoformat() if at else None,
            },
        )

    def subgraph(
        self,
        label: str,
        *,
        hops: int = 1,
        kind: str = "entity",
        at: datetime | None = None,
        limit: int = 100,
    ) -> dict:
        return self._request(
            "POST",
            "/v1/graph/subgraph",
            json={
                "label": label,
                "hops": hops,
                "kind": kind,
                "at": at.isoformat() if at else None,
                "limit": limit,
            },
        )

    def history(self, **kwargs: Any) -> list:
        return self._request("POST", "/v1/graph/history", json=kwargs)

    def drain_outbox(self) -> dict:
        return self._request("POST", "/v1/admin/outbox:drain")

    def health(self) -> dict:
        return self._request("GET", "/healthz")
