from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    configured: bool
    reachable: bool
    model: str = ""
    local: bool = False
    supports_tools: bool = False
    supports_structured_output: bool = False
    detail: str = ""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIRequest:
    request_id: str
    system_prompt: str
    messages: list[dict[str, str]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    temperature: float = 0.2
    max_tokens: int = 1400
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    text: str = ""
    provider: str = ""
    model: str = ""
    local: bool = False
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    structured: dict[str, Any] | None = None
    error: str = ""
    finish_reason: str = ""
    estimated_cost_usd: float = 0.0


@dataclass
class SourceReference:
    title: str
    source: str = ""
    source_type: str = ""
    authority_level: int = 99
    page_or_section: str = ""
    url: str = ""
    effective_date: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "source_type": self.source_type,
            "authority_level": self.authority_level,
            "page_or_section": self.page_or_section,
            "url": self.url,
            "effective_date": self.effective_date,
            "updated_at": self.updated_at,
        }


Grounding = Literal["data", "knowledge", "mixed", "general", "deterministic"]


@dataclass
class AgentResult:
    answer: str
    summary: str = ""
    priority: str = "normal"
    confidence: float = 0.0
    grounding: Grounding = "general"
    sources: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    local: bool = False
    fallback_used: bool = False
    fallback_reason: str = ""
    datasets: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    data_freshness: dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    read_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "summary": self.summary or self.answer[:240],
            "priority": self.priority,
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 3),
            "grounding": self.grounding,
            "sources": self.sources,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "missing_data": self.missing_data,
            "provider": self.provider,
            "model": self.model,
            "local": self.local,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "datasets": self.datasets,
            "tool_calls": self.tool_calls,
            "data_freshness": self.data_freshness,
            "request_id": self.request_id,
            "read_only": True,
        }


AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "summary": {"type": "string"},
        "priority": {"type": "string"},
        "confidence": {"type": "number"},
        "grounding": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "missing_data": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer"],
    "additionalProperties": True,
}
