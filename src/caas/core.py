"""Scoped memory and context assembly reference implementation."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
import hashlib

@dataclass(frozen=True)
class Principal:
    tenant: str
    subject: str
    groups: frozenset[str] = frozenset()

@dataclass(frozen=True)
class ContextItem:
    id: str
    tenant: str
    scope: str
    owner: str
    text: str
    source: str
    classification: str = "internal"
    version: int = 1
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class Store(Protocol):
    def put(self, item: ContextItem) -> None: ...
    def search(self, tenant: str, query: str) -> list[ContextItem]: ...

class MemoryStore:
    """Development-only adapter; not a secure production database."""
    def __init__(self): self.items: dict[str, ContextItem] = {}
    def put(self, item: ContextItem) -> None: self.items[item.id] = item
    def search(self, tenant: str, query: str) -> list[ContextItem]:
        words = set(query.lower().split())
        return sorted((x for x in self.items.values() if x.tenant == tenant and words.intersection(x.text.lower().split())), key=lambda x: x.timestamp, reverse=True)

def authorized(principal: Principal, item: ContextItem) -> bool:
    if principal.tenant != item.tenant: return False
    if item.scope == "personal": return principal.subject == item.owner
    if item.scope == "team": return item.owner in principal.groups
    return False

class ContextService:
    def __init__(self, store: Store): self.store = store
    def remember(self, principal: Principal, scope: str, owner: str, text: str, source: str) -> ContextItem:
        if scope not in ("personal", "team"): raise ValueError("Unsupported write scope")
        item_id = hashlib.sha256(f"{principal.tenant}:{scope}:{owner}:{source}:{text}".encode()).hexdigest()[:24]
        item = ContextItem(item_id, principal.tenant, scope, owner, text, source)
        if not authorized(principal, item): raise PermissionError("Write denied")
        self.store.put(item)
        return item
    def retrieve(self, principal: Principal, query: str, max_chars: int = 4000) -> dict:
        items = [x for x in self.store.search(principal.tenant, query) if authorized(principal, x)]
        selected, remaining = [], max_chars
        for item in items:
            if len(item.text) <= remaining:
                selected.append(item); remaining -= len(item.text)
        return {"context": "\n\n".join(x.text for x in selected), "manifest": [{"id": x.id, "source": x.source, "version": x.version} for x in selected]}
