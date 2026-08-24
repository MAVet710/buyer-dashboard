from __future__ import annotations

from sqlalchemy import create_engine

from services.ai.retrieval.retrieval import KnowledgeRetriever
from services.ai.retrieval.store import KnowledgeScope, KnowledgeStore


def knowledge_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (
            id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL,
            title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL,
            authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL,
            effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL,
            version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL,
            active BOOLEAN NOT NULL
        )""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (
            id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL,
            facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL,
            content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL
        )""")
    return engine


def add_source(store: KnowledgeStore, scope: KnowledgeScope, *, title: str, source_type: str, authority: int, effective: str, text_value: str) -> None:
    document = store.add_document(
        scope=scope,
        title=title,
        source="Massachusetts Cannabis Control Commission" if authority == 1 else "Facility",
        source_type=source_type,
        authority_level=authority,
        jurisdiction="MA",
        effective_date=effective,
        version=effective,
        source_url=f"https://example.invalid/{title.replace(' ', '-').casefold()}",
    )
    store.add_chunk(
        document_id=document,
        scope=scope,
        content=text_value,
        chunk_number=0,
        authority_level=authority,
    )


def test_newer_regulation_precedes_older_guidance_for_same_retrieved_topic():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org", "facility")
    query_text = "cannabis waste witnessing documentation requirement"
    add_source(store, scope, title="Older Waste Guidance", source_type="regulatory_guidance", authority=1, effective="2021-05-01", text_value=query_text)
    add_source(store, scope, title="Current Regulation", source_type="regulation", authority=1, effective="2026-06-18", text_value=query_text)

    result = KnowledgeRetriever(store).search(scope=scope, query="waste witnessing requirement", max_authority_level=1)
    by_title = {row["title"]: row for row in result["results"]}
    assert by_title["Current Regulation"]["precedence_status"] == "preferred_authority"
    assert by_title["Older Waste Guidance"]["precedence_status"] == "older_retrieved_authority"
    assert by_title["Current Regulation"]["precedence_score"] > by_title["Older Waste Guidance"]["precedence_score"]
    assert result["precedence_conflicts"]


def test_legal_retrieval_filters_out_internal_sop_before_model_context():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org", "facility")
    query_text = "label compliance potency statement requirement"
    add_source(store, scope, title="Government Regulation", source_type="regulation", authority=1, effective="2026-06-18", text_value=query_text)
    add_source(store, scope, title="Facility Label SOP", source_type="facility_sop", authority=2, effective="2026-08-01", text_value=query_text)

    legal = KnowledgeRetriever(store).search(scope=scope, query="label compliance requirement", max_authority_level=1)
    assert [row["title"] for row in legal["results"]] == ["Government Regulation"]
    assert legal["max_authority_level"] == 1

    internal = KnowledgeRetriever(store).search(scope=scope, query="label compliance requirement", max_authority_level=2)
    assert {row["title"] for row in internal["results"]} == {"Government Regulation", "Facility Label SOP"}
