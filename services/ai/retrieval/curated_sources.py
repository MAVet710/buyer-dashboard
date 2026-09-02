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
        "agent_keys": ("extraction",),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 30,
        "active": True,
    },
    {
        "key": "cha_cultivation_learning_framework",
        "title": "CHA-Informed Cultivation Learning Framework",
        "source": "DoobieLogic framework informed by the public CHA database topic index",
        "source_type": "reference_framework",
        "authority_level": 6,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://cha.education/database/",
        "format": "md",
        "curated_path": "knowledge_sources/curated/cha_cultivation_learning_framework.md",
        "agent_keys": ("cultivation",),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 90,
        "active": True,
    },
    {
        "key": "commercial_cannabis_cultivation_academy",
        "title": "DoobieLogic Commercial Cannabis Cultivation Academy",
        "source": "DoobieLogic synthesis of peer-reviewed cannabis research and university/extension education",
        "source_type": "research_synthesis",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://hemp.cals.cornell.edu/resources/educational-modules/",
        "format": "md",
        "curated_path": "knowledge_sources/curated/commercial_cannabis_cultivation_academy.md",
        "agent_keys": ("cultivation",),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 60,
        "active": True,
    },
    {
        "key": "professional_agent_evidence_framework",
        "title": "DoobieLogic Professional Agent Evidence Framework",
        "source": "DoobieLogic independent professional-evidence framework",
        "source_type": "professional_framework",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.gao.gov/greenbook",
        "format": "md",
        "curated_path": "knowledge_sources/curated/professional_agent_evidence_framework.md",
        "agent_keys": ("ops", "buyer", "purchasing", "inventory", "audit", "compliance", "nomenclature", "repack", "coman", "extraction", "commercial", "wholesale", "commercial_finance", "data_hub"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 90,
        "active": True,
    },
    {
        "key": "operations_manufacturing_academy",
        "title": "DoobieLogic Operations and Manufacturing Academy",
        "source": "DoobieLogic synthesis of NIST MEP and operations-management principles",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.nist.gov/mep/lean-and-process-improvement",
        "format": "md",
        "curated_path": "knowledge_sources/curated/operations_manufacturing_academy.md",
        "agent_keys": ("ops", "coman", "repack"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 90,
        "active": True,
    },
    {
        "key": "buying_purchasing_inventory_academy",
        "title": "DoobieLogic Buying, Purchasing, and Inventory Academy",
        "source": "DoobieLogic synthesis of NIST MEP supply-chain and inventory principles",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.nist.gov/mep/supply-chain",
        "format": "md",
        "curated_path": "knowledge_sources/curated/buying_purchasing_inventory_academy.md",
        "agent_keys": ("buyer", "purchasing", "inventory"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 90,
        "active": True,
    },
    {
        "key": "traceability_audit_masterdata_academy",
        "title": "DoobieLogic Traceability, Audit, and Master Data Academy",
        "source": "DoobieLogic synthesis of GAO internal-control/data-reliability and GS1 traceability principles",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard",
        "format": "md",
        "curated_path": "knowledge_sources/curated/traceability_audit_masterdata_academy.md",
        "agent_keys": ("audit", "nomenclature", "repack", "inventory", "commercial", "wholesale"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 120,
        "active": True,
    },
    {
        "key": "compliance_safety_academy",
        "title": "DoobieLogic Compliance and Safety Academy",
        "source": "DoobieLogic synthesis of NIOSH, EPA, OSHA, and governed cannabis compliance concepts",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.cdc.gov/niosh/cannabis/about/index.html",
        "format": "md",
        "curated_path": "knowledge_sources/curated/compliance_safety_academy.md",
        "agent_keys": ("compliance", "ops", "coman", "extraction", "repack"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 30,
        "active": True,
    },
    {
        "key": "extraction_science_quality_academy",
        "title": "DoobieLogic Extraction Science and Quality Academy",
        "source": "DoobieLogic synthesis of NIST cannabis measurement science and peer-reviewed extraction engineering",
        "source_type": "research_synthesis",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.nist.gov/programs-projects/nist-tools-cannabis-laboratory-quality-assurance",
        "format": "md",
        "curated_path": "knowledge_sources/curated/extraction_science_quality_academy.md",
        "agent_keys": ("extraction",),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 90,
        "active": True,
    },
    {
        "key": "commercial_wholesale_finance_academy",
        "title": "DoobieLogic Commercial, Wholesale, and Finance Academy",
        "source": "DoobieLogic synthesis of commercial operations, managerial accounting, IRS, and FinCEN concepts",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.irs.gov/newsroom/irs-announces-launch-of-new-enforcement-campaign-highlights-importance-of-whistleblowers-and-proper-disclosure-statements",
        "format": "md",
        "curated_path": "knowledge_sources/curated/commercial_wholesale_finance_academy.md",
        "agent_keys": ("commercial", "wholesale", "commercial_finance"),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 30,
        "active": True,
    },
    {
        "key": "data_governance_academy",
        "title": "DoobieLogic Data Governance and Reliability Academy",
        "source": "DoobieLogic synthesis of GAO data reliability and modern data-governance principles",
        "source_type": "professional_academy",
        "authority_level": 4,
        "jurisdiction": "",
        "effective_date": "",
        "version": "curated 2026-09-01",
        "url": "https://www.gao.gov/products/GAO-20-283G",
        "format": "md",
        "curated_path": "knowledge_sources/curated/data_governance_academy.md",
        "agent_keys": ("data_hub",),
        "facility_scope": True,
        "global_scope": False,
        "review_every_days": 180,
        "active": True,
    },
)


def _source_path(source: dict[str, Any]) -> Path:
    raw_path = str(source.get("curated_path") or "")
    relative = Path(raw_path)
    if raw_path.startswith(("/", "\\")) or relative.is_absolute() or relative.drive or ".." in relative.parts:
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
        "reviewed_at": "2026-09-02",
        "sources": [
            {
                key: source.get(key)
                for key in (
                    "key", "title", "source", "source_type", "authority_level", "jurisdiction",
                    "effective_date", "version", "url", "format", "agent_keys", "facility_scope",
                    "review_every_days", "active"
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
