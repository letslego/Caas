"""Context compiler: budgeted multi-plane assemble()."""
from __future__ import annotations

import time
from typing import Any

from .multiscope import Principal
from .working import WorkingMemory


def _take(budget: int, text: str) -> tuple[str, int]:
    if budget <= 0:
        return "", budget
    if len(text) <= budget:
        return text, budget - len(text)
    return text[:budget], 0


def assemble_pack(
    *,
    p: Principal,
    session_id: str,
    query: str,
    scopes: list[tuple[str, str]],
    working: WorkingMemory,
    profile: dict[str, Any],
    durable: dict[str, Any],
    episodes: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
    max_chars: int = 8000,
    include_operational: bool = False,
    operational: dict[str, Any] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    budget = max_chars
    sections: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    parts: list[str] = []

    # Working
    tw = time.perf_counter()
    snap = working.get(p.tenant, p.subject, session_id)
    timings["working_ms"] = (time.perf_counter() - tw) * 1000
    if snap.turns:
        block_lines = [f"{t.role}: {t.content}" for t in snap.turns[-12:]]
        block = "\n".join(block_lines)
        text, budget = _take(budget, block)
        if text:
            sections.append({"plane": "working", "text": text, "revision": snap.revision})
            parts.append("## Working\n" + text)

    # Profile
    facts = profile.get("facts") or {}
    if facts and budget > 0:
        lines = [f"{k}={v['value']}" for k, v in facts.items()]
        text, budget = _take(budget, "; ".join(lines))
        if text:
            sections.append({"plane": "profile", "text": text, "revision": profile.get("revision")})
            parts.append("## Profile\n" + text)

    # Durable scoped
    if durable.get("context") and budget > 0:
        text, budget = _take(budget, durable["context"])
        if text:
            sections.append({"plane": "durable", "text": text})
            parts.append("## Durable memory\n" + text)
            manifest.extend(durable.get("manifest") or [])

    # Episodes
    if episodes and budget > 0:
        lines = [f"- [{e['kind']}] {e['title']}: {e['detail']}" for e in episodes[:10]]
        text, budget = _take(budget, "\n".join(lines))
        if text:
            sections.append({"plane": "episodic", "text": text})
            parts.append("## Episodes\n" + text)
            for e in episodes[:10]:
                manifest.append({"id": e["id"], "source": "episode", "scope": "episodic"})

    # Knowledge
    if knowledge and budget > 0:
        lines = [f"[{k['title']}] {k['content']}" for k in knowledge]
        text, budget = _take(budget, "\n\n".join(lines))
        if text:
            sections.append({"plane": "knowledge", "text": text})
            parts.append("## Knowledge\n" + text)
            for k in knowledge:
                manifest.append(
                    {
                        "id": k["id"],
                        "source": k["source"],
                        "scope": "knowledge/" + k["document_id"],
                    }
                )

    if include_operational and operational and budget > 0:
        text, budget = _take(budget, str(operational))
        if text:
            sections.append({"plane": "operational", "text": text})
            parts.append("## Operational\n" + text)

    timings["total_ms"] = (time.perf_counter() - t0) * 1000
    return {
        "prompt": "\n\n".join(parts),
        "sections": sections,
        "manifest": manifest,
        "timings_ms": {k: round(v, 3) for k, v in timings.items()},
        "chars_remaining": budget,
        "query": query,
        "scopes": [list(s) for s in scopes],
    }
