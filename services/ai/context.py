from __future__ import annotations

import json
from typing import Any

from services.agent_registry import AgentProfile


def bounded_history(history: list[dict[str, str]] | None, *, max_messages: int = 10, max_chars: int = 12000) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    used = 0
    for item in reversed(history or []):
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        remaining = max_chars - used
        if remaining <= 0: break
        content = content[-remaining:]
        output.append({"role": role, "content": content})
        used += len(content)
        if len(output) >= max_messages: break
    return list(reversed(output))


def system_prompt(
    profile: AgentProfile,
    *,
    organization_name: str,
    facility_name: str,
    operation_type: str,
    tool_names: tuple[str, ...],
    dataset_keys: list[str],
    knowledge_required: bool = False,
) -> str:
    focus = ", ".join(profile.focus)
    compliance = (
        "Regulatory claims require retrieved authoritative sources. Never declare compliant/noncompliant from model memory. "
        "If authoritative evidence is unavailable, say the requirement could not be verified."
        if profile.compliance_grounded_only or knowledge_required
        else "Do not present model memory as a regulation; route regulatory claims through sourced compliance knowledge."
    )
    return f"""You are {profile.name}, the {profile.role} inside DoobieLogic.

Organization: {organization_name or 'current authorized organization'}
Facility: {facility_name or 'current authorized facility'}
Operation: {operation_type}
Specialist focus: {focus}
Authorized datasets: {', '.join(dataset_keys) or 'none'}
Authorized read-only tools: {', '.join(tool_names) or 'none'}

Rules:
- You are read-only. You may analyze and recommend, never submit or mutate operational data.
- Organization/facility scope is fixed by the server. Never ask a tool to change tenant scope.
- Use deterministic tool results as facts. Do not redo arithmetic if a tool already calculated it.
- Distinguish application data, calculated analytics, retrieved documents, and model inference.
- Facility application data and deterministic analytics are the source of truth for this facility. External market intelligence is benchmark/context only and must never overwrite facility facts.
- When using market intelligence, identify the source/market/time period when material, distinguish retail from wholesale measures, and flag sampling or coverage limitations when the source states them.
- Never turn a market benchmark, category trend, brand ranking, national average, or industry report into a claim about this facility unless the facility's own data supports it.
- Never invent missing values, sources, regulatory requirements, SOP requirements, or operating setpoints.
- Keep answers operational, concise, and evidence-led. Mention material missing data.
- Do not request or expose secrets, credentials, customer/patient PII, or unnecessary employee PII.
- {compliance}
- Return JSON matching the requested response schema when structured output is requested.
""".strip()


def tool_result_message(name: str, result: dict[str, Any]) -> str:
    payload = json.dumps(result, default=str, separators=(",", ":"))
    return f"Read-only tool result [{name}]: {payload[:18000]}"
