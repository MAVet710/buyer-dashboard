from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from modules.authentication.access_context import (
    clear_tenant_cache,
    hydrate_selected_context,
    set_active_facility,
    set_active_organization,
)
from modules.navigation.product_360 import (
    build_product_360_snapshot,
    search_buyer_dash,
    stage_product_for_po,
)
from modules.navigation.workspace_shell import _buyer_groups_for_state
from services.workspace_navigation import (
    AI_INTEGRATIONS_SECTION,
    BUYER_WORKSPACE,
    FLAT_NAV_ORDER,
    INVENTORY_COUNTS_SECTION,
    MA_FLOWER_EQUIVALENCY_SECTION,
    METRC_INTEGRATIONS_SECTION,
    buyer_section_groups,
    flat_buyer_sections,
    flat_category_for_route,
    flat_navigation_parity,
)


def test_flat_navigation_preserves_every_dev_buyer_page():
    groups = buyer_section_groups(is_admin=True, user_role="dev", admin_exports_enabled=True)
    ok, missing = flat_navigation_parity(groups)
    assert ok, missing
    assert AI_INTEGRATIONS_SECTION in flat_buyer_sections("Data & Settings", groups)
    assert INVENTORY_COUNTS_SECTION in flat_buyer_sections("Inventory", groups)
    assert MA_FLOWER_EQUIVALENCY_SECTION in flat_buyer_sections("Inventory", groups)
    assert "🧾 PO Builder" in flat_buyer_sections("Purchasing", groups)
    assert "📈 Trends" in flat_buyer_sections("Reports", groups)
    assert "🧭 Compliance Q&A" in flat_buyer_sections("Compliance", groups)


def test_flat_navigation_preserves_non_dev_metrc_route():
    groups = buyer_section_groups(is_admin=False, user_role="buyer", admin_exports_enabled=True)
    ok, missing = flat_navigation_parity(groups)
    assert ok, missing
    assert METRC_INTEGRATIONS_SECTION in flat_buyer_sections("Data & Settings", groups)
    assert AI_INTEGRATIONS_SECTION not in flat_buyer_sections("Data & Settings", groups)


def test_flat_shell_respects_admin_exports_license_gate(monkeypatch):
    monkeypatch.setattr(
        "services.license_session.get_license_features",
        lambda _session: {"admin_exports": False},
    )
    groups = _buyer_groups_for_state(
        {
            "is_admin": True,
            "auth_user_role": "admin",
            "license_session_data": {"features": {"admin_exports": False}},
        }
    )
    assert "🛠️ Admin Tools" not in flat_buyer_sections("Data & Settings", groups)
    assert METRC_INTEGRATIONS_SECTION in flat_buyer_sections("Data & Settings", groups)


def test_flat_categories_use_plain_business_language():
    assert FLAT_NAV_ORDER == (
        "Home",
        "Inventory",
        "Purchasing",
        "Orders",
        "Production",
        "Reports",
        "Compliance",
        "Data & Settings",
    )
    assert flat_category_for_route(BUYER_WORKSPACE, "📊 Inventory Dashboard") == "Inventory"
    assert flat_category_for_route(BUYER_WORKSPACE, "🧾 PO Builder") == "Purchasing"
    assert flat_category_for_route(BUYER_WORKSPACE, "📈 Trends") == "Reports"


def _product_state():
    return {
        "active_inventory_df": pd.DataFrame(
            [
                {
                    "Product Name": "Demo State Labs Orchard Haze Vape 1g",
                    "SKU": "DSL-VP-OH-10",
                    "Brand": "Demo State Labs",
                    "Category": "Vapes",
                    "On Hand": 2,
                    "Unit Cost": 19.0,
                    "Retail Price": 42.0,
                    "METRC Package ID": "1A406030000TEST000001",
                }
            ]
        ),
        "active_sales_df": pd.DataFrame(
            [
                {
                    "Product Name": "Demo State Labs Orchard Haze Vape 1g",
                    "Quantity Sold": 64,
                }
            ]
        ),
    }


def test_product_360_uses_existing_inventory_and_sales_sources():
    state = _product_state()
    snapshot = build_product_360_snapshot(state, "Demo State Labs Orchard Haze Vape 1g")
    assert snapshot["on_hand"] == 2
    assert snapshot["units_sold_window"] == 64
    assert snapshot["sales_window_days"] == 30
    assert snapshot["units_sold_30d"] == 64
    assert round(snapshot["days_on_hand"], 1) == 0.9
    assert snapshot["target_units"] == 43
    assert snapshot["brand"] == "Demo State Labs"
    assert snapshot["sku"] == "DSL-VP-OH-10"
    assert snapshot["packages"] == ["1A406030000TEST000001"]
    assert round(snapshot["margin_pct"], 1) == 54.8


def test_product_360_normalizes_sales_to_loaded_transaction_window():
    state = _product_state()
    product = "Demo State Labs Orchard Haze Vape 1g"
    state["active_sales_df"] = pd.DataFrame(
        [
            {"Product Name": product, "Quantity Sold": 30, "Order Time": "2026-06-20 10:00"},
            {"Product Name": product, "Quantity Sold": 30, "Order Time": "2026-08-18 10:00"},
        ]
    )

    snapshot = build_product_360_snapshot(state, product)
    assert snapshot["sales_window_days"] == 60
    assert snapshot["units_sold_window"] == 60
    assert snapshot["units_sold_30d"] == 30
    assert snapshot["daily_velocity"] == 1
    assert snapshot["days_on_hand"] == 2
    assert snapshot["target_units"] == 19


def test_product_360_add_to_po_uses_existing_po_builder_state():
    state = _product_state()
    snapshot = build_product_360_snapshot(state, "Demo State Labs Orchard Haze Vape 1g")
    staged = stage_product_for_po(state, snapshot)

    assert state["po_items"] == [staged]
    assert staged["SKU"] == "DSL-VP-OH-10"
    assert staged["Description"] == "Demo State Labs Orchard Haze Vape 1g"
    assert staged["Quantity"] == 43
    assert staged["Price"] == 19.0
    assert staged["Total"] == 817.0

    stage_product_for_po(state, snapshot)
    assert len(state["po_items"]) == 1


def test_global_search_finds_product_and_common_tool_without_ai():
    state = _product_state()
    product_results = search_buyer_dash(state, "Orchard Haze")
    assert product_results
    assert product_results[0].kind == "Product"
    assert product_results[0].product_name == "Demo State Labs Orchard Haze Vape 1g"

    tool_results = search_buyer_dash(state, "purchase order")
    assert any(result.label == "Purchase Orders" for result in tool_results)


def test_global_search_finds_sales_only_product_by_sku_and_package():
    state = {
        "active_sales_df": pd.DataFrame(
            [
                {
                    "Product Name": "Sold Out Search Test Vape 1g",
                    "Quantity Sold": 10,
                    "SKU": "SOLD-1",
                    "Package ID": "PKG-SOLD-1",
                }
            ]
        )
    }
    sku_results = search_buyer_dash(state, "SOLD-1")
    assert sku_results
    assert sku_results[0].kind == "Product"
    assert sku_results[0].product_name == "Sold Out Search Test Vape 1g"

    package_results = search_buyer_dash(state, "PKG-SOLD-1")
    assert package_results
    assert package_results[0].product_name == "Sold Out Search Test Vape 1g"


def test_tenant_switch_clears_old_tenant_cached_data():
    state = {
        "active_organization_id": "org-a",
        "active_organization_name": "A",
        "active_facility_id": "fac-a",
        "active_facility_name": "A Facility",
        "inv_raw_df": pd.DataFrame([{"sku": "A"}]),
        "sales_raw_df": pd.DataFrame([{"sku": "A"}]),
        "_cache_inv": {"bytes": b"old"},
        "_sandbox_supabase_restored": True,
        "_context_hydrated_scope": "org-a|fac-a",
    }
    changed = set_active_organization(
        state,
        SimpleNamespace(id="org-b", name="B"),
    )
    assert changed is True
    assert state["active_organization_id"] == "org-b"
    assert state["active_facility_id"] is None
    assert "inv_raw_df" not in state
    assert "sales_raw_df" not in state
    assert "_cache_inv" not in state
    assert "_sandbox_supabase_restored" not in state
    assert "_context_hydrated_scope" not in state


def test_facility_switch_clears_old_facility_cached_data():
    state = {
        "active_organization_id": "org-a",
        "active_facility_id": "fac-a",
        "inv_raw_df": pd.DataFrame([{"sku": "A"}]),
        "_context_hydrated_scope": "org-a|fac-a",
    }
    changed = set_active_facility(
        state,
        SimpleNamespace(id="fac-b", name="Second Facility"),
    )
    assert changed is True
    assert state["active_facility_id"] == "fac-b"
    assert "inv_raw_df" not in state
    assert "_context_hydrated_scope" not in state


def test_clear_tenant_cache_leaves_auth_identity_intact():
    state = {
        "auth_user_id": "user-1",
        "auth_user_role": "dev",
        "active_organization_id": "org-a",
        "inv_raw_df": pd.DataFrame([{"sku": "A"}]),
        "ecc_run_log": pd.DataFrame([{"run": "A"}]),
    }
    clear_tenant_cache(state)
    assert state["auth_user_id"] == "user-1"
    assert state["auth_user_role"] == "dev"
    assert state["active_organization_id"] == "org-a"
    assert "inv_raw_df" not in state
    assert "ecc_run_log" not in state


def test_selecting_dev_sandbox_auto_hydrates_full_supabase_source_set(monkeypatch):
    state = {
        "active_organization_id": "org-sandbox",
        "active_facility_id": "fac-sandbox",
        "auth_user_role": "dev",
    }
    calls = []

    def fake_seed(target_state, *, actor, force=False, today=None):
        calls.append(actor)
        target_state["inv_raw_df"] = pd.DataFrame([{"Product Name": "Sandbox Item"}])
        target_state["sales_raw_df"] = pd.DataFrame([{"Product Name": "Sandbox Item"}])
        target_state["_sandbox_supabase_restored"] = True
        return SimpleNamespace(seeded=True)

    monkeypatch.setattr("services.demo_data.ensure_full_app_demo_session", fake_seed)
    hydrated, message = hydrate_selected_context(
        state,
        organization=SimpleNamespace(id="org-sandbox", name="DEV Sandbox", slug="dev-sandbox"),
        facility=SimpleNamespace(id="fac-sandbox", name="Sandbox Facility", code="SANDBOX"),
        role="dev",
    )

    assert hydrated is True
    assert calls
    assert state["_context_hydrated_scope"] == "org-sandbox|fac-sandbox"
    assert state["_sandbox_supabase_restored"] is True
    assert not state["inv_raw_df"].empty
    assert "Supabase" in message


def test_access_context_exposes_desktop_and_mobile_org_facility_controls():
    source = Path("modules/authentication/access_context.py").read_text(encoding="utf-8")
    assert "dev_org_context" in source
    assert "facility_context" in source
    assert "mobile_dev_org_context" in source
    assert "mobile_facility_context" in source
    assert "mobile_access_context" in source
    assert "hydrate_selected_context" in source


def test_flat_shell_never_owns_tenant_ids():
    source = Path("modules/navigation/workspace_shell.py").read_text(encoding="utf-8")
    assert 'state["active_organization_id"] =' not in source
    assert 'state["active_facility_id"] =' not in source
    assert "access_context.py" in source


def test_flat_shell_has_mobile_navigation_and_true_drawer_overrides():
    source = Path("modules/navigation/workspace_shell.py").read_text(encoding="utf-8")
    assert "mobile_flat_navigation" in source
    assert "@media (max-width:768px)" in source
    assert ".st-key-buyer_section_group" in source
    assert ".st-key-buyer_section" in source
    assert ".st-key-data_mode" in source
    assert 'body div[data-testid="stDialog"] > div[role="dialog"]' in source
    assert "width:100vw !important" in source
    assert ".st-key-dev_org_context" not in source
    assert ".st-key-facility_context" not in source


def test_operations_home_contains_approved_attention_and_task_sections():
    source = Path("modules/navigation/role_home.py").read_text(encoding="utf-8")
    assert "NEEDS ATTENTION" in source
    assert "START A TASK" in source
    assert "home_task_card_" in source
    assert "home_metric_" in source
