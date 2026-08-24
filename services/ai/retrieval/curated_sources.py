from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from .embeddings import LocalEmbeddingProvider
from .ingestion import KnowledgeIngestionService
from .store import KnowledgeScope, KnowledgeStore

REPO_ROOT = Path(__file__).resolve().parents[3]
CURATED_ROOT = (REPO_ROOT / "knowledge_sources" / "curated").resolve()

_CURATED_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "key": "future4200_extraction_improvement_field_notes",
        "title": "Future4200 Extraction Improvement Field Notes",
        "source": "Future4200 community, curated by DoobieLogic",
        "source_type": "field_practice",
        "authority_level": 6,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-08-24",
        "url": "https://future4200.com/t/improving-extraction-efficiency/205200",
        "format": "md",
        "curated_path": "knowledge_sources/curated/future4200_extraction_field_practice.md",
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 30,
        "active": True,
    },
)


def _source_path(source: dict[str, Any]) -> Path:
    relative = Path(str(source.get("curated_path") or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Curated knowledge path must be repository-relative.")
    resolved = (REPO_ROOT / relative).resolve()
    if CURATED_ROOT not in resolved.parents:
        raise ValueError("Curated knowledge path must remain under knowledge_sources/curated.")
    if resolved.suffix.casefold() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Curated knowledge must be Markdown or text.")
    return resolved


def public_curated_catalog() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "reviewed_at": "2026-08-24",
        "sources": [
            {
                key: source.get(key)
                for key in (
                    "key", "title", "source", "source_type", "authority_level", "jurisdiction",
                    "effective_date", "version", "url", "format", "facility_scope", "review_every_days", "active"
                )
            }
            for source in _CURATED_SOURCES
            if bool(source.get("active", True))
        ],
    }


def seed_curated_sources(
    *,
    store: KnowledgeStore,
    scope: KnowledgeScope,
    embeddings: LocalEmbeddingProvider | None = None,
    keys: set[str] | None = None,
    force_reindex: bool = False,
) -> dict[str, Any]:
    ingestion = KnowledgeIngestionService(store, embeddings)
    results: list[dict[str, Any]] = []
    for source in _CURATED_SOURCES:
        if not bool(source.get("active", True)):
            continue
        key = str(source["key"])
        if keys and key not in keys:
            continue
        if not bool(source.get("facility_scope", True)) or bool(source.get("global_scope", False)):
            results.append({"key": key, "status": "rejected_scope"})
            continue
        try:
            path = _source_path(source)
            payload = path.read_bytes()
            if not payload:
                raise ValueError("Curated knowledge document is empty.")
            digest = hashlib.sha256(payload).hexdigest()
            existing = store.find_document_by_hash(scope=scope, document_hash=digest, facility_scope=True)
            if existing and not force_reindex:
                results.append({"key": key, "status": "unchanged", "document_id": existing["id"], "sha256": digest})
                continue
            result = ingestion.ingest(
                scope=scope,
                filename=path.name,
                payload=payload,
                title=str(source.get("title") or key),
                source=str(source.get("source") or path.name),
                source_type=str(source.get("source_type") or "field_practice"),
                authority_level=int(source.get("authority_level") or 6),
                jurisdiction=str(source.get("jurisdiction") or ""),
                effective_date=str(source.get("effective_date") or ""),
                version=str(source.get("version") or ""),
                source_url=str(source.get("url") or ""),
                global_scope=False,
                facility_scope=True,
            )
            store.deactivate_superseded_source(
                scope=scope,
                source_url=str(source.get("url") or ""),
                keep_document_id=str(result["document_id"]),
                facility_scope=True,
            )
            results.append({
                "key": key,
                "status": "reindexed" if existing else "indexed",
                "document_id": result["document_id"],
                "chunks": result["chunks"],
                "sha256": digest,
                "content_type": "text/markdown",
            })
        except Exception as exc:
            results.append({"key": key, "status": "failed", "error": f"{exc.__class__.__name__}: {exc}"[:500]})
    indexed = sum(1 for row in results if row["status"] in {"indexed", "reindexed"})
    unchanged = sum(1 for row in results if row["status"] == "unchanged")
    failed = sum(1 for row in results if row["status"] in {"failed", "rejected_scope"})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "indexed": indexed,
        "unchanged": unchanged,
        "failed": failed,
        "results": results,
    }
