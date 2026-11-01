"""Knowledge plane: document ingest + hybrid lexical search over chunks."""
from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .multiscope import Principal

TOKEN = re.compile(r"[a-z0-9_]+", re.I)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts = []
    i = 0
    while i < len(text):
        parts.append(text[i : i + size])
        i += max(1, size - overlap)
    return parts


class KnowledgeMixin:
    def ingest_document(
        self,
        p: Principal,
        title: str,
        content: str,
        source: str,
        *,
        visibility: str = "tenant",
    ) -> dict[str, Any]:
        self.assert_writes_allowed(p)
        if visibility not in {"tenant", "restricted"}:
            raise ValueError("invalid visibility")
        if not title.strip() or not content.strip() or not source.strip():
            raise ValueError("title/content/source required")
        doc_id = uuid.uuid4().hex
        chunks = chunk_text(content)
        self._layer_execute(
            """INSERT INTO knowledge_documents(id, tenant, title, source, visibility, owner, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (doc_id, p.tenant, title, source, visibility, p.subject, utc()),
        )
        for i, ch in enumerate(chunks):
            self._layer_execute(
                """INSERT INTO knowledge_chunks(id, document_id, tenant, ordinal, content)
                   VALUES(?,?,?,?,?)""",
                (uuid.uuid4().hex, doc_id, p.tenant, i, ch),
            )
        self._layer_commit()
        return {"id": doc_id, "title": title, "chunks": len(chunks), "source": source}

    def search_knowledge(
        self, p: Principal, query: str, *, limit: int = 8
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 50:
            raise ValueError("limit out of range")
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        rows = self._layer_fetchall(
            """SELECT c.id, c.content, c.ordinal, d.id AS document_id, d.title, d.source, d.visibility, d.owner
               FROM knowledge_chunks c
               JOIN knowledge_documents d ON d.id = c.document_id
               WHERE c.tenant=?""",
            (p.tenant,),
        )
        # Document frequency for IDF
        df: Counter[str] = Counter()
        docs_tokens: list[tuple[Any, list[str]]] = []
        for r in rows:
            if r["visibility"] == "restricted" and r["owner"] not in {None, p.subject}:
                continue
            toks = tokenize(r["content"])
            docs_tokens.append((r, toks))
            for t in set(toks):
                df[t] += 1
        n = max(1, len(docs_tokens))
        scored = []
        qset = Counter(q_tokens)
        for r, toks in docs_tokens:
            if not any(t in df and t in toks for t in q_tokens):
                continue
            tf = Counter(toks)
            score = 0.0
            for t, qf in qset.items():
                if t not in tf:
                    continue
                idf = math.log(1 + n / (1 + df[t]))
                score += qf * (tf[t] / len(toks)) * idf
            if score <= 0:
                continue
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, r in scored[:limit]:
            out.append(
                {
                    "id": r["id"],
                    "document_id": r["document_id"],
                    "title": r["title"],
                    "source": r["source"],
                    "ordinal": r["ordinal"],
                    "content": r["content"],
                    "score": round(score, 6),
                }
            )
        return out
