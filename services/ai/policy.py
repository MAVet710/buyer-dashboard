from __future__ import annotations

import re


DETERMINISTIC_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inventory_reorder_candidates", (r"\breorder\b", r"what should .*order", r"order quantit")),
    ("inventory_stockout_risk", (r"stock.?out", r"days? of supply", r"weeks? of supply", r"run out")),
    ("inventory_overstock", (r"over.?stock", r"too much inventory")),
    ("inventory_slow_movers", (r"slow mover", r"dead stock", r"not selling")),
    ("audit_recount_candidates", (r"recount", r"audit variance", r"count variance")),
    ("production_attainment", (r"attainment", r"planned .* actual", r"production progress")),
    ("commercial_fulfillment_risk", (r"fill rate", r"fulfillment risk", r"allocation shortage", r"due date risk")),
    ("cultivation_harvest_forecast", (r"harvest forecast", r"upcoming harvest", r"ready .*harvest")),
    ("cultivation_lifecycle_exceptions", (r"lifecycle", r"plant exception", r"missing .*harvest date")),
)

REGULATORY_PATTERN = re.compile(r"\b(compliant|compliance|regulation|regulatory|legal|law|ccc|metrc requirement|must|required by|violation|penalty)\b", re.I)
TRACEABILITY_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:package|pkg|lot|tag|barcode)\s+(?:id\s+|code\s+|number\s+)?[\"']?([A-Za-z0-9][A-Za-z0-9._:/-]{2,159})[\"']?",
    re.I,
)
TRACEABILITY_IDENTIFIER_STOPWORDS = {
    "lineage",
    "genealogy",
    "history",
    "source",
    "trace",
    "recall",
    "blast",
    "radius",
    "exposure",
    "affected",
}


def deterministic_tool_for(question: str, available_tools: tuple[str, ...]) -> str | None:
    value = str(question or "").casefold()
    available = set(available_tools)
    for tool, patterns in DETERMINISTIC_INTENTS:
        if tool in available and any(re.search(pattern, value, re.I) for pattern in patterns):
            return tool
    return None


def deterministic_tool_request(question: str, available_tools: tuple[str, ...]) -> tuple[str, dict] | None:
    """Resolve high-confidence deterministic requests, including identifier-bound traceability."""
    value = str(question or "")
    available = set(available_tools)
    candidates = [
        match.group(1).strip().rstrip(".,;:!?")
        for match in TRACEABILITY_IDENTIFIER_PATTERN.finditer(value)
        if match.group(1).strip().casefold() not in TRACEABILITY_IDENTIFIER_STOPWORDS
    ]
    identifier = candidates[-1] if candidates else ""
    if identifier and "recall_blast_radius" in available and re.search(r"\b(recall|blast\s+radius|affected|exposure)\b", value, re.I):
        return "recall_blast_radius", {"identifier": identifier}
    if identifier and "package_lineage" in available and re.search(r"\b(lineage|genealogy|trace|ancestry|source|came\s+from|history)\b", value, re.I):
        return "package_lineage", {"identifier": identifier}
    deterministic = deterministic_tool_for(value, available_tools)
    if deterministic:
        return deterministic, {}
    return None


def requires_regulatory_grounding(question: str) -> bool:
    return bool(REGULATORY_PATTERN.search(str(question or "")))
