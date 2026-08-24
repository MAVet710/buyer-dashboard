from __future__ import annotations

from typing import Any

from .cases import EvalCase


def score_case(case: EvalCase, *, answer: str, structured_valid: bool, tool_names: list[str] | None = None, sources: list[dict[str, Any]] | None = None, latency_ms: int = 0, estimated_cost_usd: float = 0.0) -> dict[str, Any]:
    normalized = str(answer or "").casefold()
    required = {fact: fact.casefold() in normalized for fact in case.required_facts}
    forbidden = {fact: fact.casefold() in normalized for fact in case.forbidden_facts}
    grounding_ok = True
    if case.requires_grounding:
        grounding_ok = any(int(source.get("authority_level") or 99) <= 2 for source in (sources or [])) or "cannot verify" in normalized
    correctness = sum(required.values()) / max(1, len(required)) if required else 1.0
    unsupported = sum(forbidden.values())
    return {
        "case": case.key,
        "agent": case.agent,
        "correctness": round(correctness, 3),
        "required_facts": required,
        "unsupported_fact_count": unsupported,
        "structured_output_valid": bool(structured_valid),
        "retrieval_grounding": grounding_ok,
        "tool_selection_valid": bool(tool_names) if case.deterministic else True,
        "latency_ms": max(0, int(latency_ms)),
        "estimated_cost_usd": max(0.0, float(estimated_cost_usd)),
        "passed": correctness == 1.0 and unsupported == 0 and structured_valid and grounding_ok,
    }
