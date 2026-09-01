from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from services.agent_registry import PROFILES
from services.ai.retrieval.approved_sources import load_approved_sources
from services.ai.retrieval.curated_sources import public_curated_catalog, seed_curated_sources
from services.ai.retrieval.store import KnowledgeScope, KnowledgeStore


def knowledge_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_documents (id TEXT PRIMARY KEY, organization_id TEXT NULL, facility_id TEXT NULL, title TEXT NOT NULL, source TEXT NOT NULL, source_type TEXT NOT NULL, authority_level INTEGER NOT NULL, jurisdiction TEXT NOT NULL, effective_date TEXT NOT NULL, retrieved_or_uploaded_at DATETIME NOT NULL, version TEXT NOT NULL, document_hash TEXT NOT NULL, source_url TEXT NOT NULL, active BOOLEAN NOT NULL)""")
        connection.exec_driver_sql("""CREATE TABLE ai_knowledge_chunks (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, organization_id TEXT NULL, facility_id TEXT NULL, chunk_number INTEGER NOT NULL, page_or_section TEXT NOT NULL, content TEXT NOT NULL, authority_level INTEGER NOT NULL, embedding_json TEXT NOT NULL)""")
    return engine


def test_cultivation_profile_requires_source_grounded_horticulture():
    profile = PROFILES["cultivation"]
    assert "integrated pest management" in profile.focus
    assert "root-zone pH, EC, moisture, irrigation, and source water" in profile.focus
    assert "source-grounded cultivation education" in profile.focus

    playbook = " ".join(profile.operating_instructions).casefold()
    assert "knowledge_search" in playbook
    assert "never scrape" in playbook
    assert "pesticide legality" in playbook
    assert "harvest readiness" in playbook
    assert "rank plausible causes" in playbook


def test_cha_framework_is_low_authority_local_reference_not_downloaded_content():
    catalog = public_curated_catalog()
    source = next(row for row in catalog["sources"] if row["key"] == "cha_cultivation_learning_framework")
    assert source["url"] == "https://cha.education/database/"
    assert source["source_type"] == "reference_framework"
    assert source["authority_level"] == 6
    assert source["facility_scope"] is True

    path = Path(__file__).resolve().parents[1] / "knowledge_sources" / "curated" / "cha_cultivation_learning_framework.md"
    text_body = path.read_text(encoding="utf-8").casefold()
    assert "independently written doobielogic cultivation study framework" in text_body
    assert "must not crawl or mirror cha" in text_body
    assert "member-only lessons" in text_body
    assert "never invent pesticide legality" in text_body
    assert "observed evidence" in text_body
    assert "ranked hypotheses" in text_body


def test_cha_domain_is_not_in_approved_web_downloader_allowlist():
    _payload, allowed_domains, _sources = load_approved_sources()
    assert "cha.education" not in allowed_domains


def test_cha_framework_seeds_only_the_requested_facility_scope():
    engine = knowledge_engine()
    store = KnowledgeStore(engine)
    scope = KnowledgeScope("org-a", "facility-a")
    keys = {"cha_cultivation_learning_framework"}

    first = seed_curated_sources(store=store, scope=scope, keys=keys)
    assert first["indexed"] == 1
    assert first["failed"] == 0

    second = seed_curated_sources(store=store, scope=scope, keys=keys)
    assert second["indexed"] == 0
    assert second["unchanged"] == 1

    documents = store.list_documents(scope=scope)
    assert len(documents) == 1
    assert documents[0]["source_type"] == "reference_framework"
    assert documents[0]["authority_level"] == 6
    assert documents[0]["scope"] == "facility"

    with engine.connect() as connection:
        chunks = connection.execute(text("SELECT content FROM ai_knowledge_chunks ORDER BY chunk_number")).scalars().all()
    combined = "\n".join(str(chunk) for chunk in chunks)
    assert "Integrated pest management" in combined
    assert "measure before recommending" in combined.casefold()
