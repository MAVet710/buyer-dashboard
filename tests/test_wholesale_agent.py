from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from services.agent_registry import PROFILES, resolve_agent_profile
from services.ai.context import system_prompt
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec
from services.ai.router import ProviderRouter
from services.ai.runtime import AgentRuntime
from services.ai.schemas import AIResponse, ProviderHealth
from services.wholesale_agent import load_wholesale_datasets


class _WholesaleStorefront:
    def __init__(self, engine):
        self.engine = engine

    def wholesale_inventory(self, organization_id, facility_id):
        return {
            "items": [{
                "lot_id": "lot-1",
                "package_id": "pkg-1",
                "lot_code": "LOT-001",
                "batch_name": "Grapezilla",
                "product_id": "product-1",
                "sku": "GRAPE-BULK",
                "name": "Grapezilla Bulk Flower",
                "item_type": "flower",
                "inventory_type": "bulk",
                "usable": 448.0,
                "reserved": 56.0,
                "production_reserved": 28.0,
                "wholesale_reserved": 28.0,
                "wholesale_committed": 14.0,
                "unit": "g",
                "location": "VAULT-A",
                "status": "released",
                "lab_testing_state": "passed",
                "coa_reference": "COA-001",
                "coa_url": "https://example.test/coa-001",
                "thca_percent": 29.4,
                "tac_percent": 31.1,
                "terpenes_percent": 3.2,
                "harvested_at": "2026-06-01",
                "produced_at": "2026-06-10",
                "received_at": "2026-06-12T00:00:00+00:00",
                "expiration_at": "2027-06-01",
                "unit_cost": 2.0,
                "suggested_price_usd": 4.0,
            }],
            "summary": {
                "sellable_lots": 1,
                "bulk_lots": 1,
                "retail_ready_lots": 0,
                "sellable_quantity": 448.0,
                "blocked_lots": 0,
            },
        }

    def list_catalog_options(self, organization_id, facility_id):
        return [{
            "product_id": "product-1",
            "sku": "GRAPE-BULK",
            "name": "Grapezilla Bulk Flower",
            "brand": "Cowboy Kush",
            "category": "Flower",
            "subcategory": "Bulk Flower",
            "strain": "Grapezilla",
            "product_format": "Bulk",
            "inventory_type": "bulk",
            "available": 448.0,
            "unit": "g",
            "suggested_price_usd": 4.0,
            "orderable": True,
            "test_preview": False,
            "lab_stats": {
                "thca": {"minimum": 29.4, "maximum": 29.4},
                "tac": {"minimum": 31.1, "maximum": 31.1},
                "terpenes": {"minimum": 3.2, "maximum": 3.2},
            },
            "primary_batch": {
                "lot_code": "LOT-001",
                "package_id": "pkg-1",
                "coa_reference": "COA-001",
                "coa_url": "https://example.test/coa-001",
                "available": 448.0,
                "received_at": "2026-06-12T00:00:00+00:00",
                "expiration_at": "2027-06-01",
            },
        }]


class _WholesaleIntelligence:
    def __init__(self, engine):
        self.engine = engine

    def snapshot(self, organization_id, facility_id):
        return {
            "summary": {
                "awaiting_customer_order_approval": 1,
                "approved_storefront_orders": 0,
                "rejected_storefront_orders": 0,
                "operational_sales_orders_open": 1,
                "low_stock_products": 0,
                "manifests_awaiting_verification": 0,
                "manifest_reconciliation_required": 0,
            },
            "orders_needing_approval": [{
                "id": "request-1",
                "status": "submitted",
                "buyer_company": "Example Dispensary",
                "buyer_license": "MR-EXAMPLE",
                "buyer_contact": "Private Person",
                "buyer_email": "private@example.test",
                "buyer_phone": "508-555-1212",
                "notes": "private free text",
                "purchase_order_reference": "PO-101",
                "requested_delivery_date": "2026-09-02",
                "requested_delivery_window": "AM",
                "estimated_subtotal": 1792.0,
                "lines": [{"name": "Grapezilla Bulk Flower", "quantity": 448.0}],
            }],
            "order_blockers": [{
                "request_id": "request-1",
                "buyer_company": "Example Dispensary",
                "reasons": [],
                "ready_for_review": True,
            }],
        }


class _CommercialRepository:
    def __init__(self, engine):
        self.engine = engine

    def list_orders(self, organization_id, facility_id):
        return [SimpleNamespace(
            id="order-1",
            partner_id="partner-1",
            order_type="sales",
            status="fulfilled",
            payment_status="paid",
            order_date="2026-08-01",
            created_at="2026-08-01T00:00:00+00:00",
        )]

    def list_order_lines(self, organization_id):
        return [SimpleNamespace(
            commercial_order_id="order-1",
            product_id="product-1",
            sku_snapshot="GRAPE-BULK",
            description="Grapezilla Bulk Flower",
            quantity=224.0,
            fulfilled_quantity=224.0,
            unit_price=4.0,
        )]

    def list_trade_partners(self, organization_id):
        return [SimpleNamespace(
            id="partner-1",
            name="Example Dispensary",
            partner_type="customer",
            license_or_registration="MR-EXAMPLE",
            payment_terms="Net 30",
        )]


class _FinanceService:
    def __init__(self, engine):
        self.engine = engine

    def ar_summary(self, organization_id, facility_id):
        return {
            "total_ar": 1250.0,
            "buckets": {"current": 1000.0, "1_30": 250.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0},
            "invoices": [{"invoice_id": "invoice-1"}],
        }


class _Provider:
    name = "local"
    local = True
    model = "test-model"

    def health(self):
        return ProviderHealth("local", True, True, self.model, True, True, True, "ok")

    def supports_tools(self):
        return True

    def supports_structured_output(self):
        return True

    def generate(self, request):
        return AIResponse(
            text='{"answer":"Use the authorized wholesale data.","summary":"wholesale"}',
            provider="local",
            model=self.model,
            local=True,
            structured={"answer": "Use the authorized wholesale data.", "summary": "wholesale"},
        )


def _access(*, commercial: bool = True):
    capabilities = frozenset({"commercial"}) if commercial else frozenset({"retail"})
    return DatasetAccessContext("org-a", "fac-a", "user-a", "admin", capabilities, operation_type="commercial", engine=object())


def test_wholesale_profile_is_domain_trained_and_auto_selected():
    profile = PROFILES["wholesale"]
    assert profile.name == "Wholesale Agent"
    assert profile.dataset_agent_key == "commercial"
    assert profile.operating_instructions
    assert resolve_agent_profile("Production Ops", "Wholesale Ops").key == "wholesale"
    assert resolve_agent_profile("Retail Ops", "Customer Portal").key == "wholesale"


def test_wholesale_system_prompt_contains_durable_sales_guardrails():
    prompt = system_prompt(
        PROFILES["wholesale"],
        organization_name="Org",
        facility_name="Facility",
        operation_type="commercial",
        tool_names=("preview_dataset",),
        dataset_keys=["wholesale_sellable_inventory"],
    )
    assert "passed COA" in prompt
    assert "positive uncommitted quantity" in prompt
    assert "Protect margin" in prompt
    assert "Never approve an order" in prompt
    assert "You are read-only" in prompt


def test_wholesale_data_feed_uses_canonical_data_and_excludes_contact_pii(monkeypatch):
    monkeypatch.setattr("services.wholesale_agent.WholesaleCommerceStorefrontService", _WholesaleStorefront)
    monkeypatch.setattr("services.wholesale_agent.StorefrontWholesaleIntelligenceService", _WholesaleIntelligence)
    monkeypatch.setattr("services.wholesale_agent.CommercialRepository", _CommercialRepository)
    monkeypatch.setattr("services.wholesale_agent.CommercialFinanceService", _FinanceService)

    datasets = load_wholesale_datasets(_access())

    expected = {
        "wholesale_sellable_inventory",
        "wholesale_catalog",
        "wholesale_operations_summary",
        "wholesale_pending_orders",
        "wholesale_order_blockers",
        "wholesale_account_history",
        "wholesale_product_demand",
        "wholesale_ar_summary",
    }
    assert expected.issubset(datasets)

    inventory = datasets["wholesale_sellable_inventory"].frame
    assert inventory.iloc[0]["coa_reference"] == "COA-001"
    assert inventory.iloc[0]["terpenes_percent"] == 3.2
    assert inventory.iloc[0]["suggested_gross_margin_pct"] == 50.0
    assert inventory.iloc[0]["usable_quantity"] == 448.0

    pending = datasets["wholesale_pending_orders"].frame
    assert pending.iloc[0]["buyer_company"] == "Example Dispensary"
    assert "buyer_email" not in pending.columns
    assert "buyer_phone" not in pending.columns
    assert "buyer_contact" not in pending.columns
    assert "notes" not in pending.columns
    serialized = pending.to_json().casefold()
    assert "private@example.test" not in serialized
    assert "508-555-1212" not in serialized
    assert "private free text" not in serialized

    accounts = datasets["wholesale_account_history"].frame
    assert accounts.iloc[0]["order_count"] == 1
    assert accounts.iloc[0]["average_order_value_usd"] == 896.0

    ar = datasets["wholesale_ar_summary"].frame
    assert ar.iloc[0]["total_ar_usd"] == 1250.0
    assert ar.iloc[0]["past_due_1_30_usd"] == 250.0


def test_wholesale_specific_datasets_require_commercial_facility_capability(monkeypatch):
    monkeypatch.setattr("services.wholesale_agent.WholesaleCommerceStorefrontService", _WholesaleStorefront)
    monkeypatch.setattr("services.wholesale_agent.StorefrontWholesaleIntelligenceService", _WholesaleIntelligence)
    monkeypatch.setattr("services.wholesale_agent.CommercialRepository", _CommercialRepository)
    monkeypatch.setattr("services.wholesale_agent.CommercialFinanceService", _FinanceService)

    assert load_wholesale_datasets(_access(commercial=False)) == {}


def test_wholesale_runtime_inherits_existing_commercial_datasets(monkeypatch):
    monkeypatch.setattr("services.wholesale_agent.load_wholesale_datasets", lambda access: {})
    registry = DatasetRegistry()
    registry.register(DatasetSpec(
        key="commercial_orders",
        domain="commercial",
        description="orders",
        loader=lambda access: pd.DataFrame([{"order_number": "SO-1", "status": "confirmed"}]),
        allowed_agents=("commercial",),
        required_capabilities=("commercial",),
        allowed_columns=("order_number", "status"),
    ))
    runtime = AgentRuntime(
        provider_router=ProviderRouter({"local": _Provider()}, order=["local"], allow_cloud_fallback=False),
        dataset_registry=registry,
    )

    result = runtime.run(
        profile=PROFILES["wholesale"],
        access=_access(),
        question="What wholesale sales orders need attention?",
    )

    assert "commercial_orders" in result.datasets
    assert result.provider == "local"
    assert result.answer == "Use the authorized wholesale data."
