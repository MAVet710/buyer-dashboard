"""Presentation helpers for the standardized DoobieLogic API v4 response."""

from __future__ import annotations

from typing import Any, Mapping


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def format_doobie_response(response: Mapping[str, Any] | None) -> str:
    """Turn the complete v4 response contract into readable Markdown."""

    payload = dict(response or {})
    answer = str(payload.get("answer") or "Doobie AI is currently unavailable.").strip()
    sections = [answer]

    if payload.get("needs_clarification"):
        missing = ", ".join(_clean_list(payload.get("missing_context")))
        note = "Doobie needs more context before it can give a grounded answer."
        if missing:
            note += f" Missing: {missing}."
        sections.append(f"> **More context needed:** {note}")

    explanation = str(payload.get("explanation") or "").strip()
    if explanation and explanation.casefold() != answer.casefold():
        sections.append(f"**Why**\n\n{explanation}")

    recommendations = _clean_list(payload.get("recommendations"))
    if recommendations:
        sections.append(
            "**Recommended actions**\n\n"
            + "\n".join(f"{index}. {item}" for index, item in enumerate(recommendations, 1))
        )

    risk_flags = _clean_list(payload.get("risk_flags"))
    if risk_flags:
        sections.append("**Risk flags**\n\n" + "\n".join(f"- {item}" for item in risk_flags))

    inefficiencies = _clean_list(payload.get("inefficiencies"))
    if inefficiencies:
        sections.append(
            "**Inefficiencies to investigate**\n\n"
            + "\n".join(f"- {item}" for item in inefficiencies)
        )

    compliance = payload.get("compliance_context")
    if isinstance(compliance, Mapping) and compliance:
        code = str(compliance.get("code") or "Unspecified jurisdiction")
        review = str(compliance.get("review_status") or "").strip()
        compliance_line = f"Jurisdiction: {code}"
        if review:
            compliance_line += f" · {review}"
        if payload.get("rule_verified") is False:
            compliance_line += " · Exact rule not verified; confirm before operational use"
        sections.append(f"**Compliance context**\n\n{compliance_line}")

    sources = _clean_list(payload.get("sources"))
    if sources:
        source_lines = []
        for source in sources:
            if source.startswith(("https://", "http://")):
                source_lines.append(f"- [{source}]({source})")
            else:
                source_lines.append(f"- {source}")
        sections.append("**Sources**\n\n" + "\n".join(source_lines))

    confidence = str(payload.get("confidence") or "").strip().title()
    route = str(payload.get("routed_mode") or payload.get("mode") or "").strip()
    routed_by = str(payload.get("routed_by") or "").strip()
    ai = payload.get("ai") if isinstance(payload.get("ai"), Mapping) else {}
    provider = str(ai.get("provider") or "").strip()
    model = str(ai.get("model") or "").strip()
    metadata = []
    if confidence:
        metadata.append(f"Confidence: {confidence}")
    if route:
        metadata.append(f"Specialist: {route.replace('_', ' ').title()}")
    if routed_by:
        metadata.append(routed_by)
    if provider:
        metadata.append(f"AI: {provider}{f' / {model}' if model else ''}")
    if metadata:
        sections.append("_" + " · ".join(metadata) + "_")

    return "\n\n---\n\n".join(sections)
