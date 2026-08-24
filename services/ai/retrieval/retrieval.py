from __future__ import annotations

from typing import Any

from .embeddings import LocalEmbeddingProvider
from .store import KnowledgeScope, KnowledgeStore


class KnowledgeRetriever:
    def __init__(self, store: KnowledgeStore, embeddings: LocalEmbeddingProvider | None = None) -> None:
        self.store = store
        self.embeddings = embeddings

    def search(self, *, scope: KnowledgeScope, query: str, limit: int = 8, authoritative_only: bool = False) -> dict[str, Any]:
        vector: list[float] = []
        if self.embeddings:
            values = self.embeddings.embed([query])
            vector = values[0] if values else []
        rows = self.store.search(scope=scope, query=query, query_embedding=vector, limit=limit, max_authority_level=2 if authoritative_only else None)
        sources = []
        for row in rows:
            sources.append({
                "title": str(row.get("title") or ""),
                "source": str(row.get("source") or ""),
                "source_type": str(row.get("source_type") or ""),
                "authority_level": int(row.get("authority_level") or 99),
                "jurisdiction": str(row.get("jurisdiction") or ""),
                "effective_date": str(row.get("effective_date") or ""),
                "updated_at": str(row.get("retrieved_or_uploaded_at") or ""),
                "version": str(row.get("version") or ""),
                "url": str(row.get("source_url") or ""),
                "page_or_section": str(row.get("page_or_section") or ""),
                "content": str(row.get("content") or "")[:5000],
                "score": float(row.get("score") or 0.0),
            })
        return {"query": query, "results": sources, "authoritative_only": authoritative_only, "retrieval_mode": "hybrid" if vector else "lexical"}
