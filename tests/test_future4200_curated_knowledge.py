from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from services.ai.retrieval.curated_sources import (
    _source_path,
    public_curated_catalog,
    seed_curated_sources,
)
from services.ai.retrieval.store import KnowledgeScope, KnowledgeStore


def knowledge_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL, effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL, version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL, active BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL, facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL, content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL)""")
    return engine


def test_future4200_curated_source_is_low_authority_field_practice():
    catalog = public_curated_catalog()
    source = next(row for row in catalog["sources"] if row["key"] == "future4200_extraction_improvement_field_notes")
    assert source["source_type"] == "field_practice"
    assert source["authority_level"] == 6
    assert source["facility_scope"] is True
    assert source["url"].startswith("https://future4200.com/")


def test_future4200_curated_source_seeds_facility_scope_and_is_idempotent():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org-a", "facility-a")

    first = seed_curated_sources(store=store, scope=scope)
    assert first["indexed"] == 1
    assert first["failed"] == 0

    second = seed_curated_sources(store=store, scope=scope)
    assert second["indexed"] == 0
    assert second["unchanged"] == 1

    documents = store.list_documents(scope=scope)
    assert len(documents) == 1
    assert documents[0]["source_type"] == "field_practice"
    assert documents[0]["authority_level"] == 6
    assert documents[0]["scope"] == "facility"

    with engine.connect() as connection:
        chunks = connection.execute(text("SELECT content, authority_level FROM ai_knowledge_chunks ORDER BY chunk_number")).mappings().all()
    assert chunks
    assert all(int(row["authority_level"]) == 6 for row in chunks)
    combined = "\n".join(str(row["content"]) for row in chunks)
    assert "Measure cannabinoid recovery" in combined
    assert "Do not use this document as a source for machine setpoints" in combined


def test_curated_source_path_cannot_escape_curated_directory():
    with pytest.raises(ValueError, match="repository-relative"):
        _source_path({"curated_path": "/tmp/evil.md"})
    with pytest.raises(ValueError, match="repository-relative"):
        _source_path({"curated_path": "knowledge_sources/curated/../../secrets.txt"})
    with pytest.raises(ValueError, match="under knowledge_sources/curated"):
        _source_path({"curated_path": "knowledge_sources/not-curated.md"})


def test_future4200_curated_document_exists_in_repository():
    source = public_curated_catalog()["sources"][0]
    path = Path(__file__).resolve().parents[1] / "knowledge_sources" / "curated" / "future4200_extraction_field_practice.md"
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# Future4200 Extraction Improvement Field Notes")
    assert source["authority_level"] == 6
