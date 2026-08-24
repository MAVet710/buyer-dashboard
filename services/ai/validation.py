from __future__ import annotations

import json
import re
from typing import Any

from .schemas import AIResponse


def parse_structured(response: AIResponse) -> dict[str, Any] | None:
    if isinstance(response.structured, dict):
        return response.structured
    text = str(response.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def validate_agent_response(response: AIResponse) -> tuple[bool, str]:
    if response.tool_calls:
        return True, "tool_calls"
    parsed = parse_structured(response)
    if parsed is None:
        return False, "malformed_structured_response"
    if not str(parsed.get("answer") or "").strip():
        return False, "missing_answer"
    for key in ("recommendations", "warnings", "missing_data"):
        value = parsed.get(key, [])
        if value is not None and not isinstance(value, list):
            return False, f"invalid_{key}"
    return True, "ok"


def compliance_grounding_valid(*, authoritative_sources: list[dict[str, Any]], requires_regulatory_claim: bool) -> tuple[bool, str]:
    if not requires_regulatory_claim:
        return True, "not_regulatory"
    verified = [source for source in authoritative_sources if int(source.get("authority_level") or 99) <= 2]
    return (bool(verified), "ok" if verified else "authoritative_source_required")
