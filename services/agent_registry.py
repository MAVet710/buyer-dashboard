"""Provider-neutral workspace AI agent identities for DoobieLogic.

AgentProfile describes business roles only. Provider selection, tools, datasets,
retrieval, and fallback are owned by services.ai.AgentRuntime.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    name: str
    role: str
    description: str
    focus: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    compliance_grounded_only: bool = False


PROFILES: dict[str, AgentProfile] = {
    "ops": AgentProfile("ops", "Operations Agent", "cross-workspace cannabis operations analyst", "Surfaces the most important operational risks and next actions from authorized DoobieLogic data.", ("operational priorities", "exceptions", "cross-workspace handoffs", "data readiness"), ("What needs my attention first?", "What operational risks are visible right now?")),
    "buyer": AgentProfile("buyer", "Buyer Agent", "cannabis retail buyer and assortment analyst", "Analyzes inventory, sales velocity, assortment, aging, and purchasing signals.", ("inventory coverage", "sales velocity", "assortment", "slow movers", "reorder priorities", "margin"), ("What should I focus on next in this section?", "Which products need buyer attention right now?", "Where is cash tied up in slow inventory?")),
    "purchasing": AgentProfile("purchasing", "Purchasing Agent", "purchase planning and budget analyst", "Turns demand, inventory, deliveries, open POs, policy, and budget context into read-only purchasing recommendations.", ("reorder quantities", "budget allocation", "delivery impact", "vendor concentration", "purchase timing"), ("What should I order next and why?", "Where should I spend the next purchasing dollars?", "Which incoming deliveries change my reorder needs?")),
    "inventory": AgentProfile("inventory", "Inventory Agent", "retail inventory health analyst", "Finds stockouts, overstock, aging inventory, receiving/count risks, and coverage problems.", ("days of supply", "overstock", "stockout risk", "aging", "inventory value", "receiving exceptions"), ("Show me the biggest inventory risks.", "What is overstocked or likely to stock out?", "Which inventory should I review today?")),
    "audit": AgentProfile("audit", "Inventory Audit Agent", "physical inventory audit and reconciliation analyst", "Analyzes retail or production audit progress, variances, recounts, and reconciliation risk without changing counts.", ("audit progress", "variance", "recounts", "scan exceptions", "cost impact", "reconciliation"), ("What are the biggest audit variances?", "Which items should I recount first?", "Summarize the current audit risk.")),
    "compliance": AgentProfile("compliance", "Compliance Agent", "compliance workflow and evidence analyst", "Organizes compliance evidence and questions while refusing to invent regulations from model memory.", ("authoritative evidence", "source gaps", "compliance questions", "documentation", "review readiness"), ("What compliance evidence is missing from the current workflow?", "Help me organize the compliance issues I should verify.", "What should be reviewed before I treat this as compliant?"), True),
    "nomenclature": AgentProfile("nomenclature", "Nomenclature Agent", "cannabis catalog naming and normalization analyst", "Helps normalize product names and detect inconsistent naming without changing the catalog.", ("product naming", "brand", "strain", "product type", "size", "category suffixes", "duplicates"), ("Which product names look inconsistent?", "Find likely duplicate or malformed product names.", "How should these items be normalized?")),
    "repack": AgentProfile("repack", "Repack Agent", "white-label flower repack economics and readiness analyst", "Analyzes source lots, package allocation, material requirements, costs, margin, yield, remaining bulk, and release readiness.", ("source lot", "package allocation", "landed cost", "packaging cost", "margin", "yield", "release readiness"), ("What is the best package mix for this lot?", "What is hurting margin in this scenario?", "What is missing before this lot is launch-ready?")),
    "coman": AgentProfile("coman", "Co-Man Production Agent", "co-manufacturing production planning analyst", "Analyzes production orders, BOMs, capacity, crew, machines, inventory, actuals, WIP, and material reservations.", ("production queue", "capacity", "crew", "machine utilization", "material availability", "attainment", "scrap", "WIP"), ("What production jobs are at risk?", "Where is the current capacity bottleneck?", "Which jobs need materials or scheduling attention?")),
    "extraction": AgentProfile("extraction", "Extraction Scientist Agent", "master chemical/process engineer, chief extraction scientist, and source-aware extraction knowledge analyst", "Combines commercial extraction engineering, run analytics, troubleshooting, process safety, quality, profitability, and source-grounded technical knowledge.", ("mass balance", "yield and stage loss", "hydrocarbon processing", "solventless", "CO2", "ethanol and solvent recovery", "distillation and isolation", "QA holds", "process safety", "method comparison", "COGS and gross margin", "source-grounded troubleshooting"), ("Which extraction runs need attention and what evidence points to the root cause?", "Compare yield, loss, QA risk, and margin by extraction method.", "Troubleshoot this run like a process engineer and tell me what measurements to check next.", "What does the loaded source material say about this extraction problem?")),
    "commercial": AgentProfile("commercial", "Commercial Agent", "orders, fulfillment, and inventory allocation analyst", "Analyzes sales/purchase orders, fulfillment, allocations, partners, lots, shipments, and commercial exceptions.", ("open orders", "due dates", "fill rate", "allocations", "inventory availability", "receipts", "shipments"), ("Which orders need attention first?", "What could prevent us from fulfilling open sales orders?", "Summarize purchasing, fulfillment, and inventory exceptions.")),
    "commercial_finance": AgentProfile("commercial_finance", "Commercial Finance Agent", "wholesale finance and profitability analyst", "Analyzes authorized A/R, invoice aging, order economics, margin, working capital, and partner/product profitability where the application has data.", ("revenue", "COGS", "gross margin", "A/R aging", "order profitability", "working capital"), ("What receivables need attention?", "Where is margin strongest or weakest?", "What is tying up working capital?")),
    "cultivation": AgentProfile("cultivation", "Cultivation Agent", "cultivation lifecycle and harvest-readiness analyst", "Analyzes plants, phases, rooms, strains, mother/source relationships, plant events, harvest timing, and handoff readiness without changing plant records.", ("plant phases", "rooms", "strain distribution", "mother relationships", "harvest readiness", "lifecycle exceptions", "inventory and production handoff"), ("What is coming up for harvest?", "Show me plant lifecycle exceptions.", "How are plants distributed by phase, room, and strain?")),
    "data_hub": AgentProfile("data_hub", "Data Hub Agent", "operational data quality and mapping analyst", "Inspects authorized source metadata for schema, mapping, completeness, freshness, provenance, and readiness problems.", ("schema", "column mapping", "missing fields", "duplicates", "data quality", "source readiness", "provenance"), ("Are my loaded files ready for DoobieLogic?", "What columns or mappings look wrong?", "Find data-quality problems before I use these reports.")),
}


def resolve_agent_profile(app_mode: str = "", section: str = "") -> AgentProfile:
    mode = str(app_mode or "").casefold()
    page = str(section or "").casefold().strip()
    combined = f"{mode} {page}"
    if page == "home": return PROFILES["ops"]
    if page in {"inventory audits", "inventory counts"} or "audit" in page: return PROFILES["audit"]
    if "cultivation" in combined or page in {"plants", "plant management", "plant events"}: return PROFILES["cultivation"]
    if "commercial finance" in combined or page in {"finance", "accounts receivable", "receivables"}: return PROFILES["commercial_finance"]
    if page in {"inventory", "production inventory", "retail product 360", "retail product master", "retail catalog admin", "production product master", "slow movers", "ma flower equivalency", "receive inventory"}: return PROFILES["inventory"]
    if page in {"buyer operations", "purchasing"}: return PROFILES["buyer"]
    if page in {"buying recommendations", "delivery performance", "purchase orders", "buying budget", "replenishment policies"}: return PROFILES["purchasing"]
    if page == "production": return PROFILES["coman"]
    if page == "extraction": return PROFILES["extraction"]
    if page in {"white label / repack", "package studio"}: return PROFILES["repack"]
    if page == "orders": return PROFILES["commercial"]
    if page in {"data & settings", "location settings", "integrations", "ai & metrc integrations", "metrc integrations"}: return PROFILES["data_hub"]
    if page in {"product name mapper", "nomenclature mapper"}: return PROFILES["nomenclature"]
    if page in {"compliance", "compliance q&a"}: return PROFILES["compliance"]
    if page == "sales & category trends": return PROFILES["buyer"]
    if page in {"executive reports", "reports"}: return PROFILES["ops"]
    if "inventory counts" in page: return PROFILES["audit"]
    if "compliance" in page: return PROFILES["compliance"]
    if "nomenclature" in page or "product name mapper" in page: return PROFILES["nomenclature"]
    if any(term in page for term in ("po builder", "purchasing budget", "delivery impact")): return PROFILES["purchasing"]
    if any(term in page for term in ("inventory dashboard", "slow movers", "flower equivalency")): return PROFILES["inventory"]
    if any(term in page for term in ("buyer intelligence", "trends")): return PROFILES["buyer"]
    if "white label" in combined or "repack" in combined: return PROFILES["repack"]
    if "co-man" in combined or "coman" in combined: return PROFILES["coman"]
    if "extraction" in combined: return PROFILES["extraction"]
    if "orders & fulfillment" in combined or "commercial" in combined: return PROFILES["commercial"]
    if "data hub" in combined: return PROFILES["data_hub"]
    if "buyer operations" in combined: return PROFILES["buyer"]
    if "home" in combined: return PROFILES["ops"]
    return PROFILES["buyer"]
