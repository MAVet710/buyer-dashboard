from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from services.ai.feedback import AgentFeedbackStore
from services.ai.mapping_memory import MappingMemory
from services.ai.retrieval import KnowledgeIngestionService, KnowledgeRetriever, KnowledgeScope, KnowledgeStore
from services.ai.telemetry import AITelemetry


def engine_with_ai_tables():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL, effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL, version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL, active BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL, facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL, content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_mapping_memory (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, facility_id TEXT NULL, dataset_type TEXT NOT NULL, source_vendor TEXT NOT NULL, normalized_source_header TEXT NOT NULL, canonical_field TEXT NOT NULL, confidence REAL NOT NULL, origin TEXT NOT NULL, last_used_at DATETIME NULL, usage_count INTEGER NOT NULL, human_approved BOOLEAN NOT NULL, schema_fingerprint TEXT NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_telemetry (id TEXT PRIMARY KEY, timestamp DATETIME NOT NULL, request_id TEXT NOT NULL, organization_id TEXT NOT NULL, facility_id TEXT NOT NULL, agent TEXT NOT NULL, task_category TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, is_local BOOLEAN NOT NULL, latency_ms INTEGER NOT NULL, tool_call_count INTEGER NOT NULL, retrieval_count INTEGER NOT NULL, estimated_input_tokens INTEGER NOT NULL, estimated_output_tokens INTEGER NOT NULL, estimated_cloud_cost_usd REAL NOT NULL, fallback_used BOOLEAN NOT NULL, fallback_reason TEXT NOT NULL, validation_result TEXT NOT NULL, success BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_agent_feedback (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, facility_id TEXT NOT NULL, created_at DATETIME NOT NULL, agent TEXT NOT NULL, normalized_task_type TEXT NOT NULL, sanitized_prompt TEXT NOT NULL, tool_names_json TEXT NOT NULL, sanitized_tool_outcomes_json TEXT NOT NULL, answer TEXT NOT NULL, user_rating INTEGER NULL, corrected_answer TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, evaluation_score REAL NULL, training_approved BOOLEAN NOT NULL)""")
    return engine


def test_rag_retrieval_filters_tenant_and_facility_before_ranking():
    engine = engine_with_ai_tables()
    store = KnowledgeStore(engine)
    scope_a = KnowledgeScope("org-a", "fac-a")
    scope_a2 = KnowledgeScope("org-a", "fac-a2")
    scope_b = KnowledgeScope("org-b", "fac-b")

    doc_a = store.add_document(scope=scope_a, title="Org A SOP", source="approved SOP", source_type="facility_sop", authority_level=2)
    store.add_chunk(document_id=doc_a, scope=scope_a, content="inventory variance recount procedure alpha", chunk_number=0, authority_level=2)
    doc_b = store.add_document(scope=scope_b, title="Org B SOP", source="private B SOP", source_type="facility_sop", authority_level=2)
    store.add_chunk(document_id=doc_b, scope=scope_b, content="inventory variance recount procedure beta", chunk_number=0, authority_level=2)
    global_doc = store.add_document(scope=scope_a, title="Government Guidance", source="regulator", source_type="government", authority_level=1, global_scope=True)
    store.add_chunk(document_id=global_doc, scope=scope_a, content="inventory variance official guidance", chunk_number=0, authority_level=1, global_scope=True)
    org_doc = store.add_document(scope=scope_a, title="Org A Policy", source="organization", source_type="internal_policy", authority_level=2, facility_scope=False)
    store.add_chunk(document_id=org_doc, scope=scope_a, content="inventory variance organization policy", chunk_number=0, authority_level=2, facility_scope=False)

    rows_a = store.search(scope=scope_a, query="inventory variance", limit=20)
    titles_a = {row["title"] for row in rows_a}
    assert "Org A SOP" in titles_a
    assert "Org A Policy" in titles_a
    assert "Government Guidance" in titles_a
    assert "Org B SOP" not in titles_a

    rows_a2 = store.search(scope=scope_a2, query="inventory variance", limit=20)
    titles_a2 = {row["title"] for row in rows_a2}
    assert "Org A SOP" not in titles_a2
    assert "Org A Policy" in titles_a2
    assert "Government Guidance" in titles_a2


def test_authoritative_retrieval_excludes_lower_authority_material():
    engine = engine_with_ai_tables()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org", "fac")
    official = store.add_document(scope=scope, title="Official", source="agency", source_type="government", authority_level=1)
    store.add_chunk(document_id=official, scope=scope, content="license inventory requirement", chunk_number=0, authority_level=1)
    forum = store.add_document(scope=scope, title="Forum", source="community", source_type="field_practice", authority_level=6)
    store.add_chunk(document_id=forum, scope=scope, content="license inventory requirement", chunk_number=0, authority_level=6)
    result = KnowledgeRetriever(store).search(scope=scope, query="license inventory requirement", authoritative_only=True)
    assert [row["title"] for row in result["results"]] == ["Official"]


def test_text_ingestion_records_document_and_chunks_without_cloud_embeddings():
    engine = engine_with_ai_tables()
    store = KnowledgeStore(engine)
    result = KnowledgeIngestionService(store, None).ingest(
        scope=KnowledgeScope("org", "fac"), filename="sop.md", payload=b"# Receiving\n\nVerify the manifest before receiving inventory.\n\n# Recount\n\nRecount unexpected variance.",
        title="Receiving SOP", source="Internal SOP", source_type="facility_sop", authority_level=2,
    )
    assert result["chunks"] >= 1
    retrieved = KnowledgeRetriever(store).search(scope=KnowledgeScope("org", "fac"), query="unexpected variance")
    assert retrieved["results"][0]["title"] == "Receiving SOP"
    assert retrieved["retrieval_mode"] == "lexical"


def test_mapping_memory_cannot_cross_tenants_or_schema_fingerprints():
    engine = engine_with_ai_tables()
    memory = MappingMemory(engine)
    columns = ["Item Description", "Available Qty"]
    memory.save(organization_id="org-a", facility_id="fac-a", dataset_type="Inventory", source_vendor="Inventory", source_header="Item Description", canonical_field="Product", columns=columns, confidence=1, origin="human", human_approved=True)
    memory.save(organization_id="org-b", facility_id="fac-b", dataset_type="Inventory", source_vendor="Inventory", source_header="Item Description", canonical_field="Other Product", columns=columns, confidence=1, origin="human", human_approved=True)
    assert memory.approved(organization_id="org-a", facility_id="fac-a", dataset_type="Inventory", source_vendor="Inventory", columns=columns) == {"Product": "Item Description"}
    assert memory.approved(organization_id="org-b", facility_id="fac-b", dataset_type="Inventory", source_vendor="Inventory", columns=columns) == {"Other Product": "Item Description"}
    assert memory.approved(organization_id="org-a", facility_id="fac-a", dataset_type="Inventory", source_vendor="Inventory", columns=[*columns, "Cost"]) == {}


def test_telemetry_aggregates_are_tenant_scoped_and_store_no_raw_prompt_column():
    engine = engine_with_ai_tables()
    telemetry = AITelemetry(engine)
    telemetry.record(request_id="a", organization_id="org-a", facility_id="fac-a", agent="inventory", task_category="stockout", provider="local", model="qwen", local=True, latency_ms=50, tool_call_count=1, retrieval_count=0, input_tokens=10, output_tokens=5, estimated_cost_usd=0, fallback_used=False, fallback_reason="", validation_result="ok", success=True)
    telemetry.record(request_id="b", organization_id="org-b", facility_id="fac-b", agent="inventory", task_category="stockout", provider="openai", model="cloud", local=False, latency_ms=100, tool_call_count=1, retrieval_count=0, input_tokens=10, output_tokens=5, estimated_cost_usd=.01, fallback_used=True, fallback_reason="timeout", validation_result="ok", success=True)
    summary = telemetry.summary("org-a", "fac-a")
    assert summary["requests"] == 1
    assert summary["local_utilization_pct"] == 100.0
    assert summary["cloud_cost_usd"] == 0
    with engine.connect() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(ai_telemetry)"))}
    assert "prompt" not in columns
    assert "answer" not in columns
    assert "tool_outcome" not in columns


def test_feedback_is_not_training_approved_and_redacts_before_storage():
    engine = engine_with_ai_tables()
    store = AgentFeedbackStore(engine)
    row_id = store.save(organization_id="org", facility_id="fac", agent="buyer", task_type="feedback", sanitized_prompt="contact person@example.com token abcdefghijklmnop", tool_names=["inventory_stockout_risk"], sanitized_tool_outcomes={"email": "private@example.com", "inventory_value": 10}, answer="Call 508-555-1234", rating=5, corrected_answer="", provider="local", model="qwen")
    with engine.connect() as connection:
        row = connection.execute(text("SELECT sanitized_prompt, sanitized_tool_outcomes_json, answer, training_approved FROM ai_agent_feedback WHERE id=:id"), {"id": row_id}).mappings().one()
    assert "person@example.com" not in row["sanitized_prompt"]
    assert "abcdefgh" not in row["sanitized_prompt"]
    assert "508-555-1234" not in row["answer"]
    assert "private@example.com" not in row["sanitized_tool_outcomes_json"]
    assert not bool(row["training_approved"])
    assert store.export_approved() == []
