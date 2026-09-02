"""Professional education mapping for DoobieLogic specialist agents.

This module intentionally lives outside ``services.ai`` so ``agent_registry`` can
consume it without importing the AI package and creating a runtime import cycle.
"""

from __future__ import annotations


SHARED_EVIDENCE_KEY = "professional_agent_evidence_framework"

AGENT_EDUCATION_SOURCE_KEYS: dict[str, tuple[str, ...]] = {
    "ops": (SHARED_EVIDENCE_KEY, "operations_manufacturing_academy"),
    "buyer": (SHARED_EVIDENCE_KEY, "buying_purchasing_inventory_academy"),
    "purchasing": (SHARED_EVIDENCE_KEY, "buying_purchasing_inventory_academy"),
    "inventory": (SHARED_EVIDENCE_KEY, "buying_purchasing_inventory_academy", "traceability_audit_masterdata_academy"),
    "audit": (SHARED_EVIDENCE_KEY, "traceability_audit_masterdata_academy"),
    "compliance": (SHARED_EVIDENCE_KEY, "compliance_safety_academy"),
    "nomenclature": (SHARED_EVIDENCE_KEY, "traceability_audit_masterdata_academy"),
    "repack": (SHARED_EVIDENCE_KEY, "traceability_audit_masterdata_academy", "operations_manufacturing_academy"),
    "coman": (SHARED_EVIDENCE_KEY, "operations_manufacturing_academy", "compliance_safety_academy"),
    "extraction": (SHARED_EVIDENCE_KEY, "extraction_science_quality_academy", "compliance_safety_academy"),
    "commercial": (SHARED_EVIDENCE_KEY, "commercial_wholesale_finance_academy", "traceability_audit_masterdata_academy"),
    "wholesale": (SHARED_EVIDENCE_KEY, "commercial_wholesale_finance_academy", "traceability_audit_masterdata_academy"),
    "commercial_finance": (SHARED_EVIDENCE_KEY, "commercial_wholesale_finance_academy"),
    "data_hub": (SHARED_EVIDENCE_KEY, "data_governance_academy"),
}

EDUCATED_AGENT_KEYS = frozenset(AGENT_EDUCATION_SOURCE_KEYS)

_DOMAIN_QUERY_HINTS: dict[str, str] = {
    "ops": "operations manufacturing throughput capacity bottleneck lean OEE maintenance changeover quality",
    "buyer": "buying assortment demand forecasting inventory coverage aging margin category management",
    "purchasing": "procurement supplier lead time total cost ownership reorder safety stock vendor scorecard",
    "inventory": "inventory coverage stockout overstock aging receiving traceability reconciliation unit of measure",
    "audit": "inventory audit internal control physical count reconciliation traceability evidence data reliability",
    "compliance": "cannabis compliance authoritative regulation evidence worker safety pesticide safety OSHA EPA NIOSH",
    "nomenclature": "master data product identity controlled vocabulary duplicate normalization unit of measure traceability",
    "repack": "repack transformation genealogy source lot output package yield loss traceability line clearance",
    "coman": "production manufacturing BOM capacity OEE changeover maintenance quality yield scheduling safety",
    "extraction": "cannabis extraction process engineering mass balance target recovery analytical quality safety",
    "commercial": "order fulfillment allocation available to promise fill rate customer demand margin traceability",
    "wholesale": "cannabis wholesale account demand pricing margin aging allocation fulfillment working capital",
    "commercial_finance": "managerial accounting gross margin contribution working capital accounts receivable cash conversion cannabis tax",
    "data_hub": "data governance reliability accuracy completeness applicability provenance lineage mapping schema freshness",
}


def academy_keys_for_agent(agent_key: str) -> tuple[str, ...]:
    return AGENT_EDUCATION_SOURCE_KEYS.get(str(agent_key or "").casefold(), ())


def education_search_query(agent_key: str, question: str) -> str:
    """Enrich broad questions with the specialist domain without changing intent."""

    key = str(agent_key or "").casefold()
    hint = _DOMAIN_QUERY_HINTS.get(key, "professional operations evidence")
    clean = str(question or "").strip()
    return f"{clean}\nProfessional domain context: {hint}" if clean else hint


def education_instructions(agent_key: str) -> tuple[str, ...]:
    """Return shared retrieval/evidence rules embedded in the agent system prompt."""

    key = str(agent_key or "").casefold()
    source_keys = academy_keys_for_agent(key)
    if not source_keys:
        return ()
    academy_text = ", ".join(source_keys)
    instructions = [
        f"Professional education is mapped to these facility-scoped Knowledge Library sources: {academy_text}.",
        "For professional education, troubleshooting, root-cause analysis, or questions asking why/how, use knowledge_search when available and prefer the mapped professional academy material over unsupported model memory.",
        "Keep facility facts, deterministic calculations, retrieved professional education, and model inference separate. Never invent a missing measurement, threshold, policy, cost, conversion, recipe, or source fact.",
        "Facility SOPs, controlled master data, applicable law/regulation, product labels, contracts, and canonical DoobieLogic records outrank general professional education.",
        "Treat cross-industry standards and examples as transferable professional concepts, not as cannabis law. State applicability limits when the source context differs from the facility, jurisdiction, process, product, equipment, accounting period, or data definition.",
        "When a recommendation depends on uncertain causation, rank plausible causes, name the next discriminating evidence, and prefer low-risk reversible controls before irreversible action.",
        "Cite the retrieved source or source title for material professional claims and say when a conclusion is only an inference. Reduce confidence when retrieval, facility data, or source applicability is incomplete.",
    ]
    if key == "compliance":
        instructions.append(
            "The compliance/safety academy is educational only and cannot satisfy the authoritative-evidence requirement for a compliant/noncompliant, legal, pesticide, labeling, transfer, testing, tax, or worker-safety conclusion. Retrieve the controlling current government/regulatory source or approved facility SOP."
        )
    return tuple(instructions)
