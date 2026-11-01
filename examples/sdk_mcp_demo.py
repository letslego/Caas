"""SDK demo against a live API. Start the API first with CAAS_UNSAFE_DEV_HEADERS=1."""
from __future__ import annotations

import os
import sys
import uuid

from caas import CaasClient

base = os.getenv("CAAS_BASE_URL", "http://127.0.0.1:8080")
with CaasClient(base, tenant="acme", subject="alice", groups=["platform"]) as c:
    try:
        print(c.health())
    except Exception as e:
        print("API not reachable:", e, file=sys.stderr)
        sys.exit(1)
    team = "sdk-" + uuid.uuid4().hex[:6]
    try:
        c.create_scope("personal", "alice")
    except Exception:
        pass
    c.create_scope("team", team)
    c.grant("team", team, "group:platform", "read")
    c.grant("team", team, "user:alice", "write")
    m = c.write_memory("team", team, "Orion depends on Apollo for launch", "chat")
    c.drain_outbox()
    c.relate("Orion", "depends_on", "Apollo", memory_id=m["id"])
    print(c.path("Orion", "Apollo"))
    print(c.subgraph("Orion", hops=1))
