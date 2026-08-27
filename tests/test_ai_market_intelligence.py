from __future__ import annotations

import json

import pandas as pd
import pytest

from services.agent_registry import PROFILES
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec
from services.ai.provider import ProviderHealth
from services.ai.retrieval.approved_sources import (
    DEFAULT_MARKET_MANIFEST,
    _source_allowed_domains,
    load_approved_sources,
    validate_manifest,
    validate_source_url,
)
from services.ai.retrieval.ingestion import extract_sections
from services.ai.router import ProviderRouter
from services.ai.runtime import AgentRuntime
from services.ai.schemas import AIResponse


class FakeProvider:
    name = "local"
    model = "test-model"
    local = True

    def __init__(self) -> None:
        self.calls = 0
        self.last_request = None

    def health(self):
        return ProviderHealth("local", True, True, self.model, True, True, True, "test")

    def generate(self, request):
        self.calls += 1
        self.last_request = request
        return AIResponse(
            text=json.dumps({"answer": "Facility result with market benchmark context.", "confidence": 0.9}),
            provider="local",
            model=self.model,
            local=True,
            structured={"answer": "Facility result with market benchmark context.", "confidence": 0.9},
        )

    def supports_tools(self):
        return True

    def supports_structured_output(self):
        return True


class FakeMarketRetriever:
    def __init__(self) -> None:
        self.calls = 0
        self.authoritative_flags: list[bool] = []

    def search(self, **kwargs):
        self.calls += 1
        self.authoritative_flags.append(bool(kwargs.get("authoritative_only")))
        return {
            "results": [
                {
                    "title": "Massachusetts Cannabis Prices and Trends",
                    "source": "Headset",
                    "source_type": "retail_market_intelligence",
                    "authority_level": 4,
                    "jurisdiction": "MA",
                    "effective_date": "2026-07",
                    "updated_at": "2026-08-04",
                    "version": "public market page",
                    "url": "https://www.headset.io/markets/massachusetts",
                    "page_or_section": "document",
                    "content": "Massachusetts category sales and pricing benchmark context.",
                    "score": 0.99,
                }
            ],
            "retrieval_mode": "test",
        }


def _access() -> DatasetAccessContext:
    return DatasetAccessContext("org-a", "fac-a", "user-a", "buyer", frozenset({"retail"}))


def _buyer_registry() -> DatasetRegistry:
    registry = DatasetRegistry()
    registry.register(DatasetSpec(
        key="inventory",
        domain="retail",
        description="inventory",
        loader=lambda _context: pd.DataFrame([{"Product Name": "A", "On Hand": 2, "Cost": 10, "Retail Price": 20}]),
        allowed_agents=("buyer",),
        required_capabilities=("retail",),
        allow_business_columns=True,
    ))
    registry.register(DatasetSpec(
        key="sales",
        domain="retail",
        description="sales",
        loader=lambda _context: pd.DataFrame([{"Product Name": "A", "Units Sold": 30}]),
        allowed_agents=("buyer",),
        required_capabilities=("retail",),
        allow_business_columns=True,
    ))
    return registry


def test_public_market_manifest_is_merged_into_default_catalog():
    payload, allowed, sources = load_approved_sources()
    keys = {str(source["key"]) for source in sources}

    assert DEFAULT_MARKET_MANIFEST.exists()
    assert "www.headset.io" in allowed
    assert "bdsa.com" in allowed
    assert "www.cannabisbenchmarks.com" in allowed
    assert "ma_ccc_average_retail_price_per_gram" in keys
    assert "headset_massachusetts_market" in keys
    assert "bdsa_2026_top_vape_brands" in keys
    assert "cannabis_benchmarks_us_spot_archive" in keys
    assert payload["reviewed_at"] >= "2026-08-26"


def test_regulatory_sources_keep_their_original_redirect_domain_boundary():
    _payload, combined_allowed, sources = load_approved_sources()
    regulatory = next(source for source in sources if int(source.get("authority_level") or 99) == 1)
    source_domains = _source_allowed_domains(regulatory, combined_allowed)

    assert "masscannabiscontrol.com" in source_domains
    assert "www.headset.io" not in source_domains
    assert "bdsa.com" not in source_domains
    with pytest.raises(ValueError):
        validate_source_url("https://www.headset.io/markets/massachusetts", source_domains)


def test_approved_source_manifest_accepts_public_json_and_csv_formats():
    payload = {
        "allowed_domains": ["data.example.test"],
        "sources": [
            {
                "key": "json-feed",
                "url": "https://data.example.test/feed.json",
                "format": "json",
                "authority_level": 4,
                "facility_scope": True,
            },
            {
                "key": "csv-feed",
                "url": "https://data.example.test/feed.csv",
                "format": "csv",
                "authority_level": 4,
                "facility_scope": True,
            },
        ],
    }
    allowed, sources = validate_manifest(payload)
    assert allowed == {"data.example.test"}
    assert [source["format"] for source in sources] == ["json", "csv"]


def test_structured_json_and_csv_are_split_into_retrievable_record_sections():
    json_sections = extract_sections(
        "market.json",
        json.dumps([
            {"month": "2026-06", "price": 3.87},
            {"month": "2026-07", "price": 3.83},
        ]).encode(),
    )
    csv_sections = extract_sections(
        "market.csv",
        b"month,price\n2026-06,3.87\n2026-07,3.83\n",
    )

    assert json_sections and "2026-07" in json_sections[0][1]
    assert csv_sections and "2026-07" in csv_sections[0][1]


def test_buyer_agent_retrieves_market_intelligence_as_secondary_knowledge():
    provider = FakeProvider()
    retriever = FakeMarketRetriever()
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
        retriever=retriever,
    )

    result = runtime.run(
        profile=PROFILES["buyer"],
        access=_access(),
        question="How is the Massachusetts vape market trending compared with what I am seeing here?",
    )

    assert retriever.calls == 1
    assert retriever.authoritative_flags == [False]
    assert result.grounding == "knowledge"
    assert result.sources[0]["source"] == "Headset"
    serialized_request = json.dumps(provider.last_request.messages)
    assert "retail_market_intelligence" in serialized_request
    assert "Headset" in serialized_request


def test_deterministic_reorder_fact_is_combined_with_retrieved_market_context():
    provider = FakeProvider()
    retriever = FakeMarketRetriever()
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=_buyer_registry(),
        retriever=retriever,
    )

    result = runtime.run(
        profile=PROFILES["buyer"],
        access=_access(),
        question="What should I order based on Massachusetts market trends?",
    )

    assert result.provider == "local"
    assert result.grounding == "mixed"
    assert "inventory_reorder_candidates" in result.tool_calls
    assert provider.calls == 1
    serialized_request = json.dumps(provider.last_request.messages)
    assert "inventory_reorder_candidates" in serialized_request
    assert "Headset" in serialized_request


def test_market_intelligence_cannot_satisfy_explicit_legal_grounding():
    provider = FakeProvider()
    retriever = FakeMarketRetriever()
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": provider}, order=["local"]),
        dataset_registry=DatasetRegistry(),
        retriever=retriever,
    )

    result = runtime.run(
        profile=PROFILES["buyer"],
        access=_access(),
        question="Is this legally compliant under Massachusetts cannabis regulations?",
    )

    assert retriever.calls == 1
    assert retriever.authoritative_flags == [True]
    assert result.provider == "deterministic"
    assert "government/regulatory source" in result.answer
    assert provider.calls == 0
