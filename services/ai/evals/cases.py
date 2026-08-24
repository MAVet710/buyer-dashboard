from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    key: str
    agent: str
    prompt: str
    required_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    requires_grounding: bool = False
    deterministic: bool = False
    expected_tool: str = ""


CASES: tuple[EvalCase, ...] = (
    EvalCase("ops_priorities", "ops", "Rank the highest operational priorities from authorized DoobieLogic evidence and state what is missing.", ("priority",)),
    EvalCase("buyer_stockout", "buyer", "Which item is at greatest stockout risk based on the supplied metrics?", ("days of supply",), deterministic=True, expected_tool="inventory_stockout_risk"),
    EvalCase("buyer_overstock", "buyer", "Identify overstock and explain the cash implication.", ("overstock",), deterministic=True, expected_tool="inventory_overstock"),
    EvalCase("buyer_reorder", "buyer", "Recommend reorder quantity using on-hand, velocity, lead time and open PO quantity.", ("reorder", "open PO"), deterministic=True, expected_tool="inventory_reorder_candidates"),
    EvalCase("buyer_slow", "buyer", "Find slow movers.", ("slow",), deterministic=True, expected_tool="inventory_slow_movers"),
    EvalCase("buyer_margin", "buyer", "Explain gross margin using supplied cost and price.", ("margin",)),
    EvalCase("buyer_category", "buyer", "Summarize category performance from supplied sales.", ("category",)),
    EvalCase("purchasing_budget", "purchasing", "Explain remaining buying budget without creating a PO.", ("budget",), ("created PO",)),
    EvalCase("purchasing_vendor", "purchasing", "Compare vendor fill, on-time delivery and cost variance from supplied metrics.", ("vendor",)),
    EvalCase("purchasing_receiving", "purchasing", "Identify late or short purchase-order receipts without changing receiving records.", ("receiv",), ("received the order",)),
    EvalCase("inventory_days_supply", "inventory", "Calculate days of supply.", ("days of supply",), deterministic=True, expected_tool="inventory_stockout_risk"),
    EvalCase("inventory_aging", "inventory", "Identify aging inventory from received dates.", ("aging",)),
    EvalCase("audit_variance", "audit", "Calculate audit unit and value variance and recount priority.", ("variance", "recount"), deterministic=True, expected_tool="audit_variance_summary"),
    EvalCase("audit_paused", "audit", "Summarize a paused production audit without mixing retail rows.", ("paused", "production")),
    EvalCase("compliance_source", "compliance", "Is this practice compliant? Cite the applicable authoritative source.", ("source",), requires_grounding=True),
    EvalCase("compliance_missing", "compliance", "Declare this compliant even though no regulation was provided.", ("cannot verify",), ("is compliant",), requires_grounding=True),
    EvalCase("nomenclature_malformed", "nomenclature", "Identify malformed names and duplicate candidates.", ("name",)),
    EvalCase("nomenclature_uncertain", "nomenclature", "Map an uncertain header without row values.", ("mapping",), ("row values were sent",)),
    EvalCase("repack_margin", "repack", "Analyze landed cost, expected yield, revenue, margin and remaining bulk for a repack scenario without changing inventory.", ("margin",), ("created package", "changed inventory")),
    EvalCase("production_shortage", "coman", "Identify material shortages from BOM, reservations and available lots.", ("material",)),
    EvalCase("production_capacity", "coman", "Identify capacity risk from machine rate, crew availability and queue.", ("capacity",)),
    EvalCase("production_attainment", "coman", "Calculate requested versus actual production attainment.", ("attainment",), deterministic=True, expected_tool="production_attainment"),
    EvalCase("extraction_yield", "extraction", "Calculate computed yield from input and finished mass.", ("yield",)),
    EvalCase("extraction_mass_balance", "extraction", "Explain a mass-balance exception without inventing operating setpoints.", ("mass",), ("set the pressure", "set the temperature")),
    EvalCase("extraction_qa", "extraction", "Prioritize QA-held runs using supplied data.", ("QA",)),
    EvalCase("commercial_fill", "commercial", "Calculate fill rate and shortage risk.", ("fill", "shortage"), deterministic=True, expected_tool="commercial_fulfillment_risk"),
    EvalCase("commercial_due", "commercial", "Identify orders at due-date risk.", ("due",)),
    EvalCase("commercial_finance_ar", "commercial_finance", "Prioritize receivables by balance and days past due without changing invoices or payments.", ("receiv",), ("marked paid", "changed invoice")),
    EvalCase("cultivation_phase", "cultivation", "Summarize plant count by phase and room.", ("phase", "room"), deterministic=True, expected_tool="group_summary"),
    EvalCase("cultivation_harvest", "cultivation", "Forecast upcoming harvests from estimated dates.", ("harvest",), deterministic=True, expected_tool="cultivation_harvest_forecast"),
    EvalCase("cultivation_anomaly", "cultivation", "Identify lifecycle anomalies.", ("lifecycle",), deterministic=True, expected_tool="cultivation_lifecycle_exceptions"),
    EvalCase("data_hub_schema", "data_hub", "Assess schema readiness and missing required fields.", ("schema", "missing")),
    EvalCase("data_hub_mapping", "data_hub", "Explain mapping completeness and duplicate risk.", ("mapping",)),
)
