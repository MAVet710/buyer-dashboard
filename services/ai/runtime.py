from __future__ import annotations

import json
import uuid
from typing import Any

from services.agent_registry import AgentProfile

from .cache import TenantCache
from .context import bounded_history, system_prompt, tool_result_message
from .datasets import DatasetAccessContext, DatasetRegistry
from .policy import deterministic_tool_for, requires_regulatory_grounding
from .provider import ProviderUnavailable
from .retrieval.citations import public_citations
from .retrieval.retrieval import KnowledgeRetriever
from .retrieval.store import KnowledgeScope
from .router import ProviderRouter
from .schemas import AGENT_RESPONSE_SCHEMA, AIRequest, AgentResult
from .telemetry import AITelemetry
from .tools import ToolRegistry
from .validation import parse_structured, validate_agent_response


_KNOWLEDGE_AWARE_AGENTS = {
    "ops",
    "buyer",
    "purchasing",
    "inventory",
    "repack",
    "coman",
    "extraction",
    "commercial",
    "commercial_finance",
    "cultivation",
    "data_hub",
}


class AgentRuntime:
    """DoobieLogic-owned runtime: authorize -> deterministic -> local -> validate -> fallback."""

    def __init__(
        self,
        *,
        provider_router: ProviderRouter,
        dataset_registry: DatasetRegistry,
        retriever: KnowledgeRetriever | None = None,
        telemetry: AITelemetry | None = None,
        cache: TenantCache | None = None,
        cloud_cost_rates: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.provider_router = provider_router
        self.dataset_registry = dataset_registry
        self.retriever = retriever
        self.telemetry = telemetry
        self.cache = cache or TenantCache()
        self.cloud_cost_rates = cloud_cost_rates or {}

    @staticmethod
    def _source_version(datasets: dict) -> str:
        return "|".join(f"{key}:{len(value.frame)}:{value.freshness}" for key, value in sorted(datasets.items()))

    @staticmethod
    def _format_deterministic(tool_name: str, result: dict[str, Any]) -> str:
        rows = result.get("rows") if isinstance(result.get("rows"), list) else []
        label = tool_name.replace("_", " ").title()
        if not rows:
            return f"{label}: no matching exceptions or candidates were found in the currently authorized data."
        preview = []
        for row in rows[:5]:
            useful = [f"{key}={value}" for key, value in list(row.items())[:6] if value not in (None, "")]
            preview.append("; ".join(useful))
        return f"{label}: {len(rows)} result(s) in the bounded analysis. " + " | ".join(preview)

    def _knowledge(self, access: DatasetAccessContext, question: str, *, authoritative_only: bool) -> dict[str, Any]:
        if self.retriever is None:
            return {"results": [], "retrieval_mode": "unavailable"}
        return self.retriever.search(
            scope=KnowledgeScope(access.organization_id, access.facility_id),
            query=question,
            limit=8,
            authoritative_only=authoritative_only,
        )

    def _record(self, *, access: DatasetAccessContext, request_id: str, profile: AgentProfile, task: str, result: AgentResult, latency_ms: int, input_tokens: int, output_tokens: int, validation: str, success: bool, retrieval_count: int) -> None:
        if self.telemetry is None:
            return
        cost = 0.0
        rates = self.cloud_cost_rates.get(result.provider)
        if rates and not result.local:
            cost = (max(0, input_tokens) / 1_000_000) * rates[0] + (max(0, output_tokens) / 1_000_000) * rates[1]
        self.telemetry.record(request_id=request_id, organization_id=access.organization_id, facility_id=access.facility_id, agent=profile.key, task_category=task, provider=result.provider, model=result.model, local=result.local, latency_ms=latency_ms, tool_call_count=len(result.tool_calls), retrieval_count=retrieval_count, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=cost, fallback_used=result.fallback_used, fallback_reason=result.fallback_reason, validation_result=validation, success=success)

    def run(
        self,
        *,
        profile: AgentProfile,
        access: DatasetAccessContext,
        question: str,
        history: list[dict[str, str]] | None = None,
        organization_name: str = "",
        facility_name: str = "",
    ) -> AgentResult:
        request_id = uuid.uuid4().hex
        datasets = self.dataset_registry.load_for_agent(profile.key, access)
        legal_regulatory = bool(requires_regulatory_grounding(question))
        compliance_grounded = bool(profile.compliance_grounded_only)
        knowledge_required = legal_regulatory or compliance_grounded
        knowledge_useful = knowledge_required or profile.key in _KNOWLEDGE_AWARE_AGENTS
        knowledge = self._knowledge(access, question, authoritative_only=knowledge_required) if knowledge_useful else {"results": []}
        citations = public_citations(list(knowledge.get("results") or []))
        required_authority = 1 if legal_regulatory else 2 if compliance_grounded else 99
        authoritative_sources = [source for source in citations if int(source.get("authority_level") or 99) <= required_authority]
        if knowledge_required and not authoritative_sources:
            if legal_regulatory:
                answer = "I can’t verify that legal or regulatory claim from a government/regulatory source currently indexed for this organization/facility. No legal conclusion was generated from model memory."
                warning = "Legal and regulatory conclusions require retrieved government/regulatory evidence."
                missing = "Applicable government regulation or regulatory guidance"
                validation = "government_source_required"
            else:
                answer = "I can’t verify that compliance claim from an approved authoritative source currently indexed for this organization/facility. No compliance conclusion was generated from model memory."
                warning = "Compliance conclusions require retrieved approved authoritative evidence."
                missing = "Applicable government/regulatory source or approved facility SOP"
                validation = "authoritative_source_required"
            result = AgentResult(
                answer=answer,
                summary="Authoritative compliance evidence is required.",
                confidence=1.0,
                grounding="knowledge",
                sources=citations,
                warnings=[warning],
                missing_data=[missing],
                provider="deterministic",
                model="policy",
                local=True,
                datasets=sorted(datasets),
                request_id=request_id,
            )
            self._record(access=access, request_id=request_id, profile=profile, task="compliance_grounding", result=result, latency_ms=0, input_tokens=0, output_tokens=0, validation=validation, success=True, retrieval_count=len(citations))
            return result

        def knowledge_search(query: str, limit: int) -> dict[str, Any]:
            if self.retriever is None:
                return {"results": [], "retrieval_mode": "unavailable"}
            return self.retriever.search(
                scope=KnowledgeScope(access.organization_id, access.facility_id),
                query=query,
                limit=limit,
                authoritative_only=bool(profile.compliance_grounded_only or requires_regulatory_grounding(query)),
            )

        tools = ToolRegistry(datasets, knowledge_search=knowledge_search if self.retriever else None)
        deterministic = deterministic_tool_for(question, tools.names())
        if deterministic:
            source_version = self._source_version(datasets)
            cache_key = self.cache.key(organization_id=access.organization_id, facility_id=access.facility_id, namespace=f"deterministic:{deterministic}", source_version=source_version, payload={"question": question.casefold()})
            tool_result = self.cache.get(cache_key)
            if tool_result is None:
                tool_result = tools.execute(deterministic, {})
                self.cache.set(cache_key, tool_result, ttl_seconds=60)
            if not tool_result.get("error"):
                result = AgentResult(
                    answer=self._format_deterministic(deterministic, tool_result), summary=deterministic.replace("_", " "), confidence=1.0,
                    grounding="deterministic", provider="deterministic", model="python/sql", local=True, datasets=sorted(datasets),
                    tool_calls=[deterministic], data_freshness={key: value.freshness for key, value in datasets.items()}, request_id=request_id,
                )
                self._record(access=access, request_id=request_id, profile=profile, task=deterministic, result=result, latency_ms=0, input_tokens=0, output_tokens=0, validation="deterministic", success=True, retrieval_count=len(citations))
                return result

        prompt = system_prompt(profile, organization_name=organization_name, facility_name=facility_name, operation_type=access.operation_type, tool_names=tools.names(), dataset_keys=sorted(datasets), knowledge_required=knowledge_required)
        messages = [*bounded_history(history), {"role": "user", "content": question}]
        if knowledge.get("results"):
            grounding_payload = [
                {
                    key: row.get(key)
                    for key in (
                        "title", "source", "source_type", "authority_level", "jurisdiction", "effective_date",
                        "updated_at", "version", "url", "page_or_section", "content"
                    )
                }
                for row in knowledge["results"]
            ]
            messages.append({"role": "user", "content": "Retrieved knowledge evidence: " + json.dumps(grounding_payload, default=str)[:16000]})
        request = AIRequest(request_id=request_id, system_prompt=prompt, messages=messages, tools=tools.schemas() if datasets else [], response_schema=AGENT_RESPONSE_SCHEMA, metadata={"agent_key": profile.key, "sanitized_context": {"datasets": sorted(datasets)}})
        used_tools: list[str] = []
        decision = None
        final_response = None
        bounded_context_used = False
        try:
            if datasets:
                try:
                    decision = self.provider_router.generate(
                        request,
                        validate=lambda response: (
                            (True, "tool_calls")
                            if response.tool_calls
                            else (bool(str(response.text or "").strip()), "direct_answer" if str(response.text or "").strip() else "empty_response")
                        ),
                        require_tools=True,
                    )
                    if not decision.response.tool_calls:
                        final_response = decision.response
                except ProviderUnavailable:
                    bounded_context_used = True
                    context_rows = {}
                    for name in list(datasets)[:12]:
                        context_rows[name] = tools.execute("preview_dataset", {"dataset": name, "limit": 5})
                    messages.append({"role": "user", "content": "Server-authorized bounded data context: " + json.dumps(context_rows, default=str)[:18000]})
                    request = AIRequest(request_id=request_id, system_prompt=prompt, messages=messages, response_schema=AGENT_RESPONSE_SCHEMA, metadata={"agent_key": profile.key, "sanitized_context": context_rows})
                    decision = self.provider_router.generate(request, validate=validate_agent_response, require_structured=True)
                    final_response = decision.response
                if decision and decision.response.tool_calls and final_response is None:
                    for call in decision.response.tool_calls[:6]:
                        outcome = tools.execute(call.name, call.arguments)
                        used_tools.append(call.name)
                        messages.append({"role": "user", "content": tool_result_message(call.name, outcome)})
                    followup = AIRequest(request_id=request_id, system_prompt=prompt, messages=messages, response_schema=AGENT_RESPONSE_SCHEMA, metadata={"agent_key": profile.key, "sanitized_context": {"tool_results_supplied": used_tools}})
                    final_decision = self.provider_router.generate(followup, validate=validate_agent_response, require_structured=True)
                    final_response = final_decision.response
                    if final_decision.fallback_used and not decision.fallback_used:
                        decision = final_decision
            else:
                decision = self.provider_router.generate(request, validate=validate_agent_response, require_structured=True)
                final_response = decision.response
        except ProviderUnavailable as exc:
            result = AgentResult(answer="DoobieLogic AI is currently unavailable. Operational pages and deterministic workflows remain available.", summary="AI provider unavailable", confidence=1.0, grounding="general", warnings=[str(exc)], provider="unavailable", local=True, datasets=sorted(datasets), request_id=request_id)
            self._record(access=access, request_id=request_id, profile=profile, task="provider_unavailable", result=result, latency_ms=0, input_tokens=0, output_tokens=0, validation="provider_unavailable", success=False, retrieval_count=len(citations))
            return result

        assert final_response is not None and decision is not None
        parsed = parse_structured(final_response) or {"answer": final_response.text}
        grounding = "mixed" if citations and used_tools else "knowledge" if citations else "data" if used_tools or bounded_context_used else "general"
        result = AgentResult(
            answer=str(parsed.get("answer") or final_response.text).strip(), summary=str(parsed.get("summary") or ""), priority=str(parsed.get("priority") or "normal"),
            confidence=float(parsed.get("confidence") or 0.0), grounding=grounding, sources=citations,
            recommendations=[str(value) for value in parsed.get("recommendations") or []][:20], warnings=[str(value) for value in parsed.get("warnings") or []][:20], missing_data=[str(value) for value in parsed.get("missing_data") or []][:20],
            provider=final_response.provider, model=final_response.model, local=final_response.local, fallback_used=decision.fallback_used, fallback_reason=decision.fallback_reason,
            datasets=sorted(datasets), tool_calls=used_tools, data_freshness={key: value.freshness for key, value in datasets.items()}, request_id=request_id,
        )
        self._record(access=access, request_id=request_id, profile=profile, task="agent_reasoning", result=result, latency_ms=final_response.latency_ms, input_tokens=final_response.input_tokens, output_tokens=final_response.output_tokens, validation="ok", success=True, retrieval_count=len(citations))
        return result
