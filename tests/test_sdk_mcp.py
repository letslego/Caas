"""SDK + API graph surface smoke tests (Postgres + httpx ASGI)."""
from __future__ import annotations

import os
import uuid

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("httpx")

DSN = os.getenv("CAAS_DATABASE_URL") or os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DSN or not DSN.startswith("postgres"),
    reason="Set CAAS_DATABASE_URL",
)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CAAS_UNSAFE_DEV_HEADERS", "1")
    monkeypatch.setenv("CAAS_DATABASE_URL", DSN)
    import importlib

    import caas.multiscope_api as api

    importlib.reload(api)
    from fastapi.testclient import TestClient

    with TestClient(api.app) as c:
        yield c


def headers(tenant, subject="alice", groups="eng"):
    return {
        "X-Verified-Tenant": tenant,
        "X-Verified-Subject": subject,
        "X-Verified-Groups": groups,
    }


def test_api_graph_endpoints(client):
    tenant = "sdk-" + uuid.uuid4().hex[:8]
    h = headers(tenant)
    assert client.get("/healthz").json()["backend"] == "PostgresMemory"

    assert client.post(
        "/v1/scopes",
        headers=h,
        json={"kind": "personal", "scope_id": "alice"},
    ).status_code == 200
    assert client.post(
        "/v1/scopes", headers=h, json={"kind": "team", "scope_id": "eng"}
    ).status_code == 200
    client.post(
        "/v1/grants",
        headers=h,
        json={
            "kind": "team",
            "scope_id": "eng",
            "subject": "group:eng",
            "permission": "read",
        },
    )
    client.post(
        "/v1/grants",
        headers=h,
        json={
            "kind": "team",
            "scope_id": "eng",
            "subject": "user:alice",
            "permission": "write",
        },
    )
    mem = client.post(
        "/v1/memories",
        headers=h,
        json={
            "kind": "team",
            "scope_id": "eng",
            "content": "Orion depends on Apollo",
            "source": "chat",
        },
    ).json()
    client.post("/v1/admin/outbox:drain", headers=h)
    rel = client.post(
        "/v1/graph/relate",
        headers=h,
        json={
            "src_label": "Orion",
            "relation": "depends_on",
            "dst_label": "Apollo",
            "memory_id": mem["id"],
        },
    ).json()
    assert rel["relation"] == "depends_on"
    path = client.post(
        "/v1/graph/path",
        headers=h,
        json={"src_label": "Orion", "dst_label": "Apollo"},
    ).json()
    assert path["found"] is True
    hist = client.post(
        "/v1/graph/history", headers=h, json={"label": "Orion"}
    ).json()
    assert len(hist) >= 1
    sub = client.post(
        "/v1/graph/subgraph", headers=h, json={"label": "Orion", "hops": 1}
    ).json()
    assert len(sub["nodes"]) >= 2


def test_sdk_headers_and_paths():
    from caas.sdk import CaasClient

    calls = []

    class Fake:
        def request(self, method, url, headers=None, **kwargs):
            calls.append((method, url, headers, kwargs))

            class R:
                status_code = 200
                content = b'{"ok":true}'

                def json(self):
                    return {"ok": True}

            return R()

        def close(self):
            pass

    sdk = CaasClient(
        "http://example",
        tenant="acme",
        subject="alice",
        groups=["eng"],
        client=Fake(),
    )
    sdk.relate("A", "links", "B")
    method, url, headers, kwargs = calls[-1]
    assert method == "POST"
    assert url.endswith("/v1/graph/relate")
    assert headers["X-Verified-Tenant"] == "acme"
    assert kwargs["json"]["src_label"] == "A"
    sdk.close()


def test_mcp_tools_registered():
    pytest.importorskip("mcp")
    from caas.mcp_server import mcp

    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert "caas_graph_relate" in names
    assert "caas_retrieve_context" in names
    assert "caas_graph_path" in names
