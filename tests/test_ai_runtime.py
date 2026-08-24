from __future__ import annotations

import json

import pandas as pd
import pytest

from services.agent_registry import PROFILES
from services.ai.analytics import audit_metrics, inventory_health, production_attainment
from services.ai.cache import TenantCache
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec
from services.ai.provider import ProviderTimeout, ProviderUnavailable
from services.ai.providers.doobie import DoobieProvider
from services.ai.providers.local import LocalOpenAIProvider
from services.ai.router import ProviderRouter
from services.ai.runtime import AgentRuntime
from services.ai.sanitization import sanitize_text
from services.ai.schemas import AIRequest, AIResponse, ProviderHealth, ToolCall
from services.ai.tools import ToolRegistry


class FakeProvider:
    def __init__(self, name: str, *, local: bool, response: AIResponse | None = None, error: Exception | None = None, tools: bool = True, structured: bool = True, reachable: bool = True):
        self.name = name
        self.local = local
        self.model = f"{name}-model"
        self.response = response or AIResponse(text='{"answer":"ok"}', provider=name, model=self.model, local=local, structured={"answer": "ok"})
        self.error = error
        self.tools = tools
        self.structured = structured
        self.reachable = reachable
        self.calls = 0

    def health(self):
        return ProviderHealth(self.name, True, self.reachable, self.model, self.local, self.tools, self.structured, "test")

    def generate(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response

    def supports_tools(self):
        return self.tools

    def supports_structured_output(self):
        return self.structured


class FakeRetriever:
    def __init__(self, authority_level: int):
        self.authority_level = authority_level

    def search(self, **kwargs):
        return {
            "results": [{
                "title": "Approved source",
                "source": "test",
                "source_type": "facility_sop" if self.authority_level == 2 else "government",
                "authority_level": self.authority_level,
                "jurisdiction": "MA",
                "effective_date": "2026-01-01",
                "updated_at": "2026-01-01",
                "version": "1",
                "url": "https://example.test/source",
                "page_or_section": "1",
                "content": "approved evidence",
                "score": 1.0,
            }],
            "retrieval_mode": "test",
        }


def request() -> AIRequest:
    return AIRequest(request_id="test", system_prompt="system", messages=[{"role": "user", "content": "hello"}], response_schema={"type": "object"})


def test_provider_router_prefers_local_without_fallback():
    local = FakeProvider("local", local=True)
    cloud = FakeProvider("gemini", local=False)
    decision = ProviderRouter({"local": local, "gemini": cloud}, order=["local", "gemini"]).generate(request())
    assert decision.response.provider == "local"
    assert decision.fallback_used is False
    assert local.calls == 1
    assert cloud.calls == 0


def test_provider_router_falls_back_on_objective_timeout():
    local = FakeProvider("local", local=True, error=ProviderTimeout("timeout"))
    cloud = FakeProvider("gemini", local=False)
    decision = ProviderRouter({"local": local, "gemini": cloud}, order=["local", "gemini"]).generate(request())
    assert decision.response.provider == "gemini"
    assert decision.fallback_used is True
    assert "local:timeout" in decision.fallback_reason


def test_provider_router_cloud_fallback_can_be_disabled():
    local = FakeProvider("local", local=True, error=ProviderTimeout("timeout"))
    cloud = FakeProvider("gemini", local=False)
    router = ProviderRouter({"local": local, "gemini": cloud}, order=["local", "gemini"], allow_cloud_fallback=False)
    with pytest.raises(ProviderUnavailable):
        router.generate(request())
    assert cloud.calls == 0


def test_provider_router_validation_failure_is_objective_fallback():
    bad = FakeProvider("local", local=True, response=AIResponse(text="bad", provider="local", model="local-model", local=True))
    good = FakeProvider("openai", local=False)
    decision = ProviderRouter({"local": bad, "openai": good}, order=["local", "openai"]).generate(request(), validate=lambda response: (response.structured is not None, "malformed_structured_response"))
    assert decision.response.provider == "openai"
    assert "validation:malformed_structured_response" in decision.fallback_reason


class FakeHTTPResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._body


def test_local_openai_compatible_provider_health_and_tool_call(monkeypatch):
    monkeypatch.setattr("services.ai.providers.local.requests.get", lambda *args, **kwargs: FakeHTTPResponse({"data": []}))
    monkeypatch.setattr("services.ai.providers.local.requests.post", lambda *args, **kwargs: FakeHTTPResponse({
        "choices": [{"message": {"content": "", "tool_calls": [{"id": "call-1", "function": {"name": "preview_dataset", "arguments": json.dumps({"dataset": "inventory"})}}]}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }))
    provider = LocalOpenAIProvider(base_url="http://local-ai:8000", model="open-weight-model")
    health = provider.health()
    assert health.configured and health.reachable and health.local
    response = provider.generate(AIRequest(request_id="x", system_prompt="system", messages=[{"role": "user", "content": "inventory"}], tools=[{"type": "function", "function": {"name": "preview_dataset", "description": "preview", "parameters": {"type": "object"}}}]))
    assert response.provider == "local"
    assert response.tool_calls == [ToolCall("call-1", "preview_dataset", {"dataset": "inventory"})]


def test_doobie_provider_normalizes_legacy_response_to_structured_output(monkeypatch):
    provider = DoobieProvider(base_url="https://doobie.example", api_key="secret")
    monkeypatch.setattr(provider.client, "copilot", lambda **kwargs: {"answer": "Use the supplied data.", "confidence": 0.8})
    response = provider.generate(request())
    assert provider.supports_structured_output() is True
    assert response.provider == "doobie"
    assert response.structured["answer"] == "Use the supplied data."
    assert response.structured["confidence"] == pytest.approx(0.8)


def test_dataset_registry_enforces_role_capability_and_sensitive_columns():
    registry = DatasetRegistry()
    registry.register(DatasetSpec(
        key="inventory",
        domain="retail",
        description="inventory",
        loader=lambda context: pd.DataFrame([{"Product Name": "A", "Unit Cost": 5.0, "email": "person@example.com", "api_key": "secret"}]),
        allowed_agents=("inventory",),
        allowed_roles=("buyer",),
        required_capabilities=("retail",),
        allow_business_columns=True,
    ))
    denied_role = DatasetAccessContext("org-a", "fac-a", "user-a", "operator", frozenset({"retail"}))
    denied_cap = DatasetAccessContext("org-a", "fac-a", "user-a", "buyer", frozenset({"production"}))
    allowed = DatasetAccessContext("org-a", "fac-a", "user-a", "buyer", frozenset({"retail"}))
    assert registry.load_for_agent("inventory", denied_role) == {}
    assert registry.load_for_agent("inventory", denied_cap) == {}
    loaded = registry.load_for_agent("inventory", allowed)["inventory"].frame
    assert "Product Name" in loaded.columns
    assert "Unit Cost" in loaded.columns
    assert "email" not in loaded.columns
    assert "api_key" not in loaded.columns


def test_tool_schemas_never_offer_tenant_scope_as_model_argument():
    spec = DatasetSpec(key="inventory", domain="retail", description="inventory", loader=lambda context: pd.DataFrame([{"Product Name": "A", "On Hand": 2}]), allowed_agents=("inventory",), allow_business_columns=True)
    registry = DatasetRegistry()
    registry.register(spec)
    access = DatasetAccessContext("org-a", "fac-a", "u", "buyer", frozenset({"retail"}))
    tools = ToolRegistry(registry.load_for_agent("inventory", access))
    serialized = json.dumps(tools.schemas()).casefold()
    assert "organization_id" not in serialized
    assert "facility_id" not in serialized
    assert "user_id" not in serialized


def test_deterministic_inventory_question_runs_with_zero_model_providers():
    registry = DatasetRegistry()
    registry.register(DatasetSpec(key="inventory", domain="retail", description="inventory", loader=lambda context: pd.DataFrame([{"Product Name": "A", "On Hand": 7, "Cost": 10, "Retail Price": 20}]), allowed_agents=("inventory",), required_capabilities=("retail",), allow_business_columns=True))
    registry.register(DatasetSpec(key="sales", domain="retail", description="sales", loader=lambda context: pd.DataFrame([{"Product Name": "A", "Units Sold": 30}]), allowed_agents=("inventory",), required_capabilities=("retail",), allow_business_columns=True))
    runtime = AgentRuntime(provider_router=ProviderRouter({}, order=[], allow_cloud_fallback=False), dataset_registry=registry)
    result = runtime.run(profile=PROFILES["inventory"], access=DatasetAccessContext("org-a", "fac-a", "u", "buyer", frozenset({"retail"})), question="What is the days of supply and stockout risk?")
    assert result.provider == "deterministic"
    assert result.model == "python/sql"
    assert result.local is True
    assert "inventory_stockout_risk" in result.tool_calls
    assert result.answer.startswith("Inventory Stockout Risk")


def test_compliance_agent_refuses_regulatory_conclusion_without_authoritative_source():
    provider = FakeProvider("local", local=True)
    runtime = AgentRuntime(provider_router=ProviderRouter({"local": provider}, order=["local"]), dataset_registry=DatasetRegistry())
    result = runtime.run(profile=PROFILES["compliance"], access=DatasetAccessContext("org-a", "fac-a", "u", "qa", frozenset({"retail"})), question="Is this legally compliant?")
    assert "can’t verify" in result.answer
    assert result.provider == "deterministic"
    assert provider.calls == 0


def test_legal_regulatory_claim_rejects_level_two_sop_evidence():
    provider = FakeProvider("local", local=True)
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
        retriever=FakeRetriever(2),
    )
    result = runtime.run(
        profile=PROFILES["compliance"],
        access=DatasetAccessContext("org-a", "fac-a", "u", "qa", frozenset({"retail"})),
        question="Is this legal under Massachusetts cannabis regulation?",
    )
    assert "government/regulatory source" in result.answer
    assert provider.calls == 0


def test_internal_compliance_question_accepts_level_two_approved_sop_evidence():
    provider = FakeProvider("local", local=True, tools=False)
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
        retriever=FakeRetriever(2),
    )
    result = runtime.run(
        profile=PROFILES["compliance"],
        access=DatasetAccessContext("org-a", "fac-a", "u", "qa", frozenset({"retail"})),
        question="Does this follow our approved facility SOP?",
    )
    assert result.provider == "local"
    assert provider.calls == 1


def test_tenant_cache_keys_cannot_cross_organization_or_facility():
    first = TenantCache.key(organization_id="org-a", facility_id="fac-a", namespace="x", source_version="v1", payload={"q": 1})
    other_org = TenantCache.key(organization_id="org-b", facility_id="fac-a", namespace="x", source_version="v1", payload={"q": 1})
    other_facility = TenantCache.key(organization_id="org-a", facility_id="fac-b", namespace="x", source_version="v1", payload={"q": 1})
    assert len({first, other_org, other_facility}) == 3


def test_sanitized_feedback_text_redacts_common_pii_and_credentials():
    value = sanitize_text("Email me at person@example.com or 508-555-1234. token abcdefghijklmnop SSN 123-45-6789")
    assert "person@example.com" not in value
    assert "508-555-1234" not in value
    assert "abcdefgh" not in value
    assert "123-45-6789" not in value


def test_deterministic_formulas_use_canonical_production_and_audit_fields():
    inventory = pd.DataFrame([{"Product Name": "A", "On Hand": 10, "Cost": 2, "Retail Price": 5}])
    sales = pd.DataFrame([{"Product Name": "A", "Units Sold": 30}])
    health = inventory_health(inventory, sales, sales_days=30)
    assert health.iloc[0]["days_of_supply"] == pytest.approx(10.0)
    assert health.iloc[0]["gross_margin_pct"] == pytest.approx(60.0)

    audit = audit_metrics(pd.DataFrame([{"expected_quantity": 10, "counted_quantity": 8, "unit_cost": 5}]))
    assert audit.iloc[0]["variance_units"] == pytest.approx(-2.0)
    assert audit.iloc[0]["variance_value"] == pytest.approx(-10.0)

    attainment = production_attainment(pd.DataFrame([{"id": "p1", "requested_units": 100}]), pd.DataFrame([{"production_order_id": "p1", "actual_units": 80}]))
    assert attainment.iloc[0]["attainment_pct"] == pytest.approx(80.0)
