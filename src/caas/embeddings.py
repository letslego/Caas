"""Embedding providers for pgvector projection.

Production deployments should inject a real model (OpenAI, Voyage, Vertex, …).
`HashingEmbedder` is a deterministic local stand-in so offline tests and demos
can exercise vector recall without network credentials.
"""
from __future__ import annotations

import hashlib
import math
import os
import struct
from typing import Protocol


class Embedder(Protocol):
    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Signed feature-hashing embedder (L2-normalized). Not semantically strong."""

    def __init__(self, dim: int = 384, model: str = "hashing-v1"):
        if dim < 8:
            raise ValueError("dim must be >= 8")
        self.dim = dim
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in text.casefold().split():
            digest = hashlib.sha256(tok.encode()).digest()
            # Use first 8 bytes for index, next 8 for sign/magnitude seed.
            idx = struct.unpack_from(">I", digest, 0)[0] % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def vector_literal(values: list[float]) -> str:
    """Render a pgvector text literal bound as text and cast with ::vector."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def default_embedder() -> Embedder:
    dim = int(os.getenv("CAAS_EMBED_DIM", "384"))
    model = os.getenv("CAAS_EMBED_MODEL", "hashing-v1")
    return HashingEmbedder(dim=dim, model=model)
