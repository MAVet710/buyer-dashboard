from __future__ import annotations

from typing import Any

from .embeddings import LocalEmbeddingProvider
from .store import KnowledgeScope, KnowledgeStore


class KnowledgeRetriever:
    def __init__(self, store: KnowledgeStore, embeddings: LocalEmbeddingProvider | None = None) -> None:
        self.store = store
        self.embeddings = embeddings

    @staticmethod
    def _annotate_precedence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for row in rows:
            row["precedence_status"] = "normal"
        authoritative = [row for row in rows if int(row.get("authority_level") or 99) <= 2]
        if len(authoritative) < 2:
            if authoritative:
                authoritative[0]["precedence_status"] = "preferred_authority"
            return rows

        by_jurisdiction: dict[str, list[dict[str, Any]]] = {}
        for row in authoritative:
            key = str(row.get("jurisdiction") or "").casefold().strip()
            by_jurisdiction.setdefault(key, []).append(row)
        for group in by_jurisdiction.values():
            if not group:
                continue
            preferred = max(
                group,
                key=lambda row: (
                    -int(row.get("authority_level") or 99),
                    float(row.get("precedence_score") or 0.0),
                    KnowledgeStore._effective_timestamp(row.get("effective_date")),
                    str(row.get("retrieved_or_uploaded_at") or ""),
                ),
            )
            preferred["precedence_status"] = "preferred_authority"
            preferred_time = KnowledgeStore._effective_timestamp(preferred.get("effective_date"))
            for row in group:
                if row is preferred:
                    continue
                row_time = KnowledgeStore._effective_timestamp(row.get("effective_date"))
                if preferred_time and row_time and row_time < preferred_time:
                    row["precedence_status"] = "older_retrieved_authority"
                else:
                    row["precedence_status"] = "secondary_authority"
        return rows

    def search(
        self,
        *,
        scope: KnowledgeScope,
        query: str,
        limit: int = 8,
        authoritative_only: bool = False,
        max_authority_level: int | None = None,
    ) -> dict[str, Any]:
        vector: list[float] = []
        if self.embeddings:
            values = self.embeddings.embed([query])
            vector = values[0] if values else []
        authority_limit = max_authority_level if max_authority_level is not None else 2 if authoritative_only else None
        rows = self.store.search(
            scope=scope,
            query=query,
            query_embedding=vector,
            limit=limit,
            max_authority_level=authority_limit,
        )
        rows = self._annotate_precedence(rows)
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
                "precedence_score": float(row.get("precedence_score") or 0.0),
                "precedence_status": str(row.get("precedence_status") or "normal"),
            })
        conflicts = [
            {
                "title": source["title"],
                "effective_date": source["effective_date"],
                "status": source["precedence_status"],
            }
            for source in sources
            if source["precedence_status"] in {"older_retrieved_authority", "secondary_authority"}
        ]
        return {
            "query": query,
            "results": sources,
            "authoritative_only": bool(authority_limit is not None),
            "max_authority_level": authority_limit,
            "precedence_conflicts": conflicts,
            "retrieval_mode": "hybrid" if vector else "lexical",
        }
