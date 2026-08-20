from __future__ import annotations

from datetime import date
import math

import pandas as pd

import modules.navigation.product_360 as p360
import modules.navigation.product_360_master as p360_master


def _state() -> dict:
    return {
        "active_organization_id": "org-1",
        "active_inventory_df": pd.DataFrame(
            [
                {
                    "Product": "GMO Pre-Roll 1g",
                    "SKU": "OLD-SKU",
                    "Available": 10,
                    "Reserved": 0,
                    "Cost": 2.0,
                    "Retail Price": 10.0,
                    "Vendor": "Report Vendor",
                    "Category": "Old Category",
                    "Package ID": "PKG-1",
                }
            ]
        ),
        "active_sales_df": pd.DataFrame(
            [
                {
                    "Product": "GMO Pre-Roll 1g",
                    "Quantity Sold": 30,
                    "Report Start": "2026-07-21",
                    "Report End": "2026-08-19",
                }
            ]
        ),
    }


def _master() -> dict:
    return {
        "canonical_product_id": "product-1",
        "product_name": "GMO Pre-Roll 1g",
        "sku": "GMO-PR-1G",
        "brand": "House Brand",
        "category": "Pre-Rolls",
        "subcategory": "Singles",
        "strain": "GMO",
        "manufacturer": "Buyer Dash Manufacturing",
        "product_format": "1g pre-roll",
        "description": "Canonical product description",
        "primary_vendor": "Acme Cannabis Supply",
        "primary_vendor_id": "vendor-1",
        "vendor_sku": "ACME-GMO-001",
        "vendor_lead_time_days": 12,
        "vendor_moq": 24.0,
        "vendor_case_pack": 12.0,
        "unit_cost": 4.0,
        "retail_price": 16.0,
        "external_mappings": [
            {"system_name": "metrc", "external_id": "ITEM-123", "external_name": "GMO PR"}
        ],
        "aliases": ["GMO PR 1 Gram"],
        "value_history": [
            {
                "effective_at": "2026-08-01T00:00:00+00:00",
                "value_type": "unit_cost",
                "amount": 4.0,
                "previous_amount": 3.5,
                "currency": "USD",
                "source": "purchase_order",
                "source_reference": "PO-1001",
            }
        ],
    }


def test_product_360_patch_is_installed_at_navigation_boundary():
    assert getattr(p360, "_product_master_patch_installed", False) is True


def test_product_360_uses_canonical_identity_vendor_values_and_order_constraints(monkeypatch):
    monkeypatch.setattr(p360_master, "_load_master_context", lambda *args, **kwargs: _master())

    snapshot = p360.build_product_360_snapshot(_state(), "GMO Pre-Roll 1g")

    assert snapshot["canonical_product_id"] == "product-1"
    assert snapshot["sku"] == "GMO-PR-1G"
    assert snapshot["brand"] == "House Brand"
    assert snapshot["category"] == "Pre-Rolls"
    assert snapshot["strain"] == "GMO"
    assert snapshot["vendor"] == "Acme Cannabis Supply"
    assert snapshot["unit_cost"] == 4.0
    assert snapshot["retail_price"] == 16.0
    assert snapshot["margin_pct"] == 75.0
    assert snapshot["inventory_value"] == 40.0
    assert snapshot["retail_value"] == 160.0

    # 30 sold across 30 days with 10 on hand creates an 11-unit 21-day raw gap.
    assert snapshot["raw_target_units"] == 11
    assert snapshot["target_units"] == 24
    assert snapshot["estimated_reorder_cost"] == 96.0
    assert snapshot["decision_signal"] == "ORDER NOW"
    assert "12-day vendor lead time" in snapshot["decision_reason"]
    assert "rounds the 11-unit need to 24" in snapshot["decision_reason"]
    assert snapshot["recommended_order_date"] == date.today().isoformat()


def test_zero_days_on_hand_stays_urgent_with_vendor_lead_time():
    base = {
        "product_name": "Out Product",
        "on_hand": 0.0,
        "days_on_hand": 0.0,
        "target_units": 7,
        "unit_cost": 2.0,
        "retail_price": 8.0,
        "decision_signal": "ORDER NOW",
        "decision_reason": "Out of stock.",
    }
    master = {
        "canonical_product_id": "p-out",
        "product_name": "Out Product",
        "vendor_lead_time_days": 5,
        "vendor_moq": 0,
        "vendor_case_pack": 0,
    }
    enriched = p360_master.enrich_product_360_snapshot(base, master)
    assert enriched["days_on_hand"] == 0.0
    assert enriched["decision_signal"] == "ORDER NOW"
    assert enriched["recommended_order_date"] == date.today().isoformat()


def test_vendor_constraints_always_round_up():
    assert p360_master._apply_vendor_constraints(11, moq=24, case_pack=12) == 24
    assert p360_master._apply_vendor_constraints(25, moq=0, case_pack=12) == 36
    assert p360_master._apply_vendor_constraints(13, moq=0, case_pack=12.5) == 25
    assert p360_master._apply_vendor_constraints(0, moq=24, case_pack=12) == 0


def test_global_search_can_return_canonical_product_without_loaded_reports(monkeypatch):
    monkeypatch.setattr(
        p360_master,
        "_load_master_search",
        lambda *args, **kwargs: [_master()],
    )
    results = p360.search_buyer_dash(
        {"active_organization_id": "org-1"},
        "GMO",
        limit=8,
    )
    assert results
    assert results[0].kind == "Product"
    assert results[0].label == "GMO Pre-Roll 1g"
    assert results[0].product_name == "GMO Pre-Roll 1g"
    assert "House Brand" in results[0].subtitle
    assert "GMO-PR-1G" in results[0].subtitle


def test_global_search_dedupes_master_and_report_product_punctuation(monkeypatch):
    master = _master()
    master["product_name"] = "GMO Pre Roll 1g"
    monkeypatch.setattr(
        p360_master,
        "_load_master_search",
        lambda *args, **kwargs: [master],
    )
    state = _state()
    results = p360.search_buyer_dash(state, "GMO", limit=8)
    product_results = [row for row in results if row.kind == "Product"]
    normalized = [p360_master._norm(row.product_name or row.label) for row in product_results]
    assert normalized.count("gmo pre roll 1g") == 1


def test_missing_master_context_preserves_report_fallback(monkeypatch):
    monkeypatch.setattr(p360_master, "_load_master_context", lambda *args, **kwargs: {})
    snapshot = p360.build_product_360_snapshot(_state(), "GMO Pre-Roll 1g")
    assert snapshot.get("canonical_product_id", "") == ""
    assert snapshot["sku"] == "OLD-SKU"
    assert snapshot["vendor"] == "Report Vendor"
    assert snapshot["unit_cost"] == 2.0
    assert snapshot["retail_price"] == 10.0
    assert math.isfinite(snapshot["days_on_hand"])
