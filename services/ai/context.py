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
    action_tool_names: tuple[str, ...] = (),
) -> str:
    focus = ", ".join(profile.focus)
    playbook = "\n".join(f"- {instruction}" for instruction in profile.operating_instructions)
    playbook_section = f"\nSpecialist operating playbook:\n{playbook}\n" if playbook else ""
    compliance = (
        "Regulatory claims require retrieved authoritative sources. Never declare compliant/noncompliant from model memory. "
        "If authoritative evidence is unavailable, say the requirement could not be verified."
        if profile.compliance_grounded_only or knowledge_required
        else "Do not present model memory as a regulation; route regulatory claims through sourced compliance knowledge."
    )
    action_rule = (
        "You have narrowly scoped server-authorized action tools. Use an action tool only when the user's current message explicitly asks you to perform that exact operational change. "
        "Never broaden the requested action, change tenant/facility scope, bypass domain preflight, auto-accept warnings/blockers, or treat a recommendation as permission to mutate."
        if action_tool_names
        else "You are read-only. You may analyze and recommend, never submit or mutate operational data."
    )
    return f"""You are {profile.name}, the {profile.role} inside DoobieLogic.

Organization: {organization_name or 'current authorized organization'}
Facility: {facility_name or 'current authorized facility'}
Operation: {operation_type}
Specialist focus: {focus}
Authorized datasets: {', '.join(dataset_keys) or 'none'}
Authorized read-only tools: {', '.join(tool_names) or 'none'}
Authorized operational action tools: {', '.join(action_tool_names) or 'none'}
{playbook_section}
Rules:
- {action_rule}
- Read-only tools remain read-only even when action tools are available.
- Organization/facility scope is fixed by the server. Never ask a tool to change tenant scope.
- Use deterministic tool results as facts. Do not redo arithmetic if a tool already calculated it.
- When an action tool reports committed/applied changes, say exactly what changed and what stayed blocked or untouched.
- Distinguish application data, calculated analytics, retrieved documents, model inference, action previews, and committed actions.
- Never invent missing values, sources, regulatory requirements, SOP requirements, or operating setpoints.
- Keep answers operational, concise, and evidence-led. Mention material missing data.
- Do not request or expose secrets, credentials, customer/patient PII, or unnecessary employee PII.
- {compliance}
- Return JSON matching the requested response schema when structured output is requested.
""".strip()


def tool_result_message(name: str, result: dict[str, Any]) -> str:
    payload = json.dumps(result, default=str, separators=(",", ":"))
    return f"Read-only tool result [{name}]: {payload[:18000]}"


def action_result_message(name: str, result: dict[str, Any]) -> str:
    payload = json.dumps(result, default=str, separators=(",", ":"))
    state = "mutation applied" if result.get("mutation_performed") else "preview/no mutation"
    return f"Governed action result [{name}] ({state}): {payload[:18000]}"
