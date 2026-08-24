from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text

from services.ai.retrieval.approved_sources import seed_approved_sources
from services.ai.retrieval.store import KnowledgeScope, KnowledgeStore


def knowledge_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL, effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL, version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL, active BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL, facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL, content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL)""")
    return engine


def test_library_listing_is_tenant_and_facility_scoped_without_identifier_leakage():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    a1 = KnowledgeScope("org-a", "fac-a1")
    a2 = KnowledgeScope("org-a", "fac-a2")
    b1 = KnowledgeScope("org-b", "fac-b1")

    store.add_document(scope=a1, title="A1 SOP", source="internal", source_type="facility_sop", authority_level=2)
    store.add_document(scope=a2, title="A2 SOP", source="internal", source_type="facility_sop", authority_level=2)
    store.add_document(scope=b1, title="B1 SOP", source="private", source_type="facility_sop", authority_level=2)
    store.add_document(scope=a1, title="Org A Policy", source="internal", source_type="internal_policy", authority_level=2, facility_scope=False)
    store.add_document(scope=a1, title="Global Reference", source="public", source_type="technical_reference", authority_level=4, global_scope=True)

    rows = store.list_documents(scope=a1)
    titles = {row["title"] for row in rows}
    assert titles == {"A1 SOP", "Org A Policy", "Global Reference"}
    assert "A2 SOP" not in titles
    assert "B1 SOP" not in titles
    assert all("organization_id" not in row and "facility_id" not in row for row in rows)
    assert {row["scope"] for row in rows} == {"facility", "organization", "global"}


def test_approved_seed_is_idempotent_and_supersedes_changed_content(tmp_path: Path, monkeypatch):
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org", "facility")
    manifest = {
        "allowed_domains": ["masscannabiscontrol.com"],
        "sources": [{
            "key": "official_test",
            "title": "Official Test Guidance",
            "source": "Massachusetts Cannabis Control Commission",
            "source_type": "regulatory_guidance",
            "authority_level": 1,
            "jurisdiction": "MA",
            "effective_date": "2026-06-18",
            "version": "v1",
            "url": "https://masscannabiscontrol.com/test",
            "format": "html",
            "facility_scope": True,
            "global_scope": False,
            "active": True,
        }],
    }
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    state = {"payload": b"<html><body>Official inventory rule version one.</body></html>"}

    def fake_download(source, *, allowed_domains):
        assert allowed_domains == {"masscannabiscontrol.com"}
        return state["payload"], source["url"], "text/html"

    monkeypatch.setattr("services.ai.retrieval.approved_sources.download_source", fake_download)

    first = seed_approved_sources(store=store, scope=scope, manifest_path=manifest_path)
    assert first["indexed"] == 1
    assert first["unchanged"] == 0
    assert first["failed"] == 0

    second = seed_approved_sources(store=store, scope=scope, manifest_path=manifest_path)
    assert second["indexed"] == 0
    assert second["unchanged"] == 1
    assert len(store.list_documents(scope=scope)) == 1

    state["payload"] = b"<html><body>Official inventory rule version two.</body></html>"
    third = seed_approved_sources(store=store, scope=scope, manifest_path=manifest_path)
    assert third["indexed"] == 1
    assert third["unchanged"] == 0
    assert len(store.list_documents(scope=scope)) == 1
    with engine.connect() as connection:
        active = connection.execute(text("SELECT COUNT(*) FROM ai_knowledge_documents WHERE active")).scalar_one()
        total = connection.execute(text("SELECT COUNT(*) FROM ai_knowledge_documents")).scalar_one()
    assert active == 1
    assert total == 2


def test_force_reindex_keeps_only_one_active_document(tmp_path: Path, monkeypatch):
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org", "facility")
    manifest = {
        "allowed_domains": ["support.dutchie.com"],
        "sources": [{
            "key": "dutchie_test",
            "title": "Dutchie Test",
            "source": "Dutchie Help Center",
            "source_type": "dutchie",
            "authority_level": 3,
            "jurisdiction": "",
            "effective_date": "",
            "version": "current",
            "url": "https://support.dutchie.com/test",
            "format": "html",
            "facility_scope": True,
            "global_scope": False,
            "active": True,
        }],
    }
    manifest_path = tmp_path / "sources.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    payload = b"<html><body>Dutchie inventory workflow.</body></html>"
    monkeypatch.setattr(
        "services.ai.retrieval.approved_sources.download_source",
        lambda source, allowed_domains: (payload, source["url"], "text/html"),
    )

    seed_approved_sources(store=store, scope=scope, manifest_path=manifest_path)
    result = seed_approved_sources(store=store, scope=scope, manifest_path=manifest_path, force_reindex=True)
    assert result["results"][0]["status"] == "reindexed"
    assert len(store.list_documents(scope=scope)) == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM ai_knowledge_documents WHERE active")).scalar_one() == 1
