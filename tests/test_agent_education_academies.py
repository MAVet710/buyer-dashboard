from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from services.agent_education import (
    AGENT_EDUCATION_SOURCE_KEYS,
    EDUCATED_AGENT_KEYS,
    academy_keys_for_agent,
    education_instructions,
    education_search_query,
)
from services.agent_registry import PROFILES
from services.ai.context import system_prompt
from services.ai.retrieval.curated_sources import public_curated_catalog, seed_curated_sources
from services.ai.retrieval.store import KnowledgeScope, KnowledgeStore


ACADEMY_KEYS = {
    "professional_agent_evidence_framework",
    "operations_manufacturing_academy",
    "buying_purchasing_inventory_academy",
    "traceability_audit_masterdata_academy",
    "compliance_safety_academy",
    "extraction_science_quality_academy",
    "commercial_wholesale_finance_academy",
    "data_governance_academy",
}

EXPECTED_EDUCATED_AGENTS = {
    "ops",
    "buyer",
    "purchasing",
    "inventory",
    "audit",
    "compliance",
    "nomenclature",
    "repack",
    "coman",
    "extraction",
    "commercial",
    "wholesale",
    "commercial_finance",
    "data_hub",
}


def knowledge_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL, effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL, version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL, active BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL, facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL, content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL)""")
    return engine


def test_all_non_cultivation_specialists_have_professional_education_mapping():
    assert set(EDUCATED_AGENT_KEYS) == EXPECTED_EDUCATED_AGENTS
    assert set(AGENT_EDUCATION_SOURCE_KEYS) == EXPECTED_EDUCATED_AGENTS
    assert "cultivation" not in EDUCATED_AGENT_KEYS
    assert set(PROFILES) >= EXPECTED_EDUCATED_AGENTS | {"cultivation"}

    for agent_key in EXPECTED_EDUCATED_AGENTS:
        mapped = academy_keys_for_agent(agent_key)
        assert mapped
        assert mapped[0] == "professional_agent_evidence_framework"
        assert len(mapped) == len(set(mapped))
        assert set(mapped) <= ACADEMY_KEYS


def test_catalog_exposes_facility_scoped_academies_and_audience_map():
    catalog = public_curated_catalog()
    by_key = {row["key"]: row for row in catalog["sources"]}
    assert ACADEMY_KEYS <= set(by_key)

    for key in ACADEMY_KEYS:
        source = by_key[key]
        assert source["facility_scope"] is True
        assert int(source["authority_level"]) == 4
        assert source["source_type"] in {"professional_framework", "professional_academy", "research_synthesis"}
        assert source["agent_keys"]
        assert source["review_every_days"] >= 1

    # Educational syntheses must never be promoted into the authoritative
    # compliance levels used for law/regulator grounding.
    assert all(int(by_key[key]["authority_level"]) > 2 for key in ACADEMY_KEYS)
    assert set(by_key["compliance_safety_academy"]["agent_keys"]) >= {"compliance", "coman", "extraction"}
    assert set(by_key["traceability_audit_masterdata_academy"]["agent_keys"]) >= {"audit", "nomenclature", "repack"}


def test_academy_documents_cover_expected_professional_domains_and_sources():
    root = Path(__file__).resolve().parents[1] / "knowledge_sources" / "curated"
    expectations = {
        "professional_agent_evidence_framework.md": ("Evidence order", "model inference", "Source and licensing posture"),
        "operations_manufacturing_academy.md": ("Overall equipment effectiveness", "Total productive maintenance", "https://www.nist.gov/mep/lean-and-process-improvement"),
        "buying_purchasing_inventory_academy.md": ("Reorder point", "Total cost of ownership", "https://www.nist.gov/mep/supply-chain"),
        "traceability_audit_masterdata_academy.md": ("Data reliability", "Transformation genealogy", "https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard"),
        "compliance_safety_academy.md": ("authority boundary", "Worker Protection Standard", "https://www.cdc.gov/niosh/cannabis/about/index.html"),
        "extraction_science_quality_academy.md": ("Mass balance", "Analytical measurement quality", "https://www.nist.gov/programs-projects/nist-tools-cannabis-laboratory-quality-assurance"),
        "commercial_wholesale_finance_academy.md": ("Available-to-promise", "Cannabis federal tax context", "https://www.fincen.gov/resources/statutes-regulations/guidance/bsa-expectations-regarding-marijuana-related-businesses"),
        "data_governance_academy.md": ("accuracy", "provenance", "https://www.gao.gov/products/GAO-20-283G"),
    }
    for filename, needles in expectations.items():
        body = (root / filename).read_text(encoding="utf-8")
        for needle in needles:
            assert needle.casefold() in body.casefold(), f"{filename} missing {needle}"


def test_professional_education_is_injected_into_agent_system_prompt():
    buyer = system_prompt(
        PROFILES["buyer"],
        organization_name="Org A",
        facility_name="Facility A",
        operation_type="Retail",
        tool_names=("knowledge_search", "inventory_reorder_candidates"),
        dataset_keys=["inventory", "sales"],
    )
    assert "buying_purchasing_inventory_academy" in buyer
    assert "use knowledge_search" in buyer.casefold()
    assert "unsupported model memory" in buyer.casefold()

    wholesale = system_prompt(
        PROFILES["wholesale"],
        organization_name="Org A",
        facility_name="Facility A",
        operation_type="Production",
        tool_names=("knowledge_search",),
        dataset_keys=["commercial_orders"],
    )
    assert "commercial_wholesale_finance_academy" in wholesale
    # Existing specialist playbook must remain present alongside education.
    assert "canonical Wholesale storefront projection" in wholesale

    compliance = system_prompt(
        PROFILES["compliance"],
        organization_name="Org A",
        facility_name="Facility A",
        operation_type="Production",
        tool_names=("knowledge_search",),
        dataset_keys=[],
        knowledge_required=True,
    )
    assert "compliance_safety_academy" in compliance
    assert "cannot satisfy the authoritative-evidence requirement" in compliance
    assert "Never declare compliant/noncompliant from model memory" in compliance


def test_education_query_preserves_question_and_adds_domain_context():
    query = education_search_query("data_hub", "Why do the inventory totals disagree?")
    assert "Why do the inventory totals disagree?" in query
    assert "provenance" in query
    assert "lineage" in query

    instructions = " ".join(education_instructions("extraction")).casefold()
    assert "knowledge_search" in instructions
    assert "facility facts" in instructions
    assert "model inference" in instructions


def test_selected_academies_seed_only_to_requested_facility_and_are_idempotent():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope_a = KnowledgeScope("org-a", "facility-a")
    scope_b = KnowledgeScope("org-a", "facility-b")
    keys = {"operations_manufacturing_academy", "data_governance_academy"}

    first = seed_curated_sources(store=store, scope=scope_a, keys=keys)
    assert first["indexed"] == 2
    assert first["failed"] == 0

    second = seed_curated_sources(store=store, scope=scope_a, keys=keys)
    assert second["indexed"] == 0
    assert second["unchanged"] == 2

    docs_a = store.list_documents(scope=scope_a)
    docs_b = store.list_documents(scope=scope_b)
    assert len(docs_a) == 2
    assert docs_b == []
    assert {doc["title"] for doc in docs_a} == {
        "DoobieLogic Operations and Manufacturing Academy",
        "DoobieLogic Data Governance and Reliability Academy",
    }
    assert all(doc["scope"] == "facility" for doc in docs_a)
    assert all(int(doc["authority_level"]) == 4 for doc in docs_a)
