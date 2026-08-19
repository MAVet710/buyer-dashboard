from pathlib import Path

import pandas as pd

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
    assert snapshot["units_sold_30d"] == 64
    assert round(snapshot["days_on_hand"], 1) == 0.9
    assert snapshot["target_units"] == 43
    assert snapshot["brand"] == "Demo State Labs"
    assert snapshot["sku"] == "DSL-VP-OH-10"
    assert snapshot["packages"] == ["1A406030000TEST000001"]
    assert round(snapshot["margin_pct"], 1) == 54.8


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

    # A double-click / rerun must not create an identical duplicate line.
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


def test_access_context_stays_a_sidebar_org_and_facility_switcher():
    source = Path("modules/authentication/access_context.py").read_text(encoding="utf-8")
    assert 'st.sidebar.selectbox("Organization"' in source
    assert 'st.sidebar.selectbox("Facility"' in source
    assert "active_organization_id" in source
    assert "active_facility_id" in source


def test_flat_shell_never_owns_tenant_ids():
    source = Path("modules/navigation/workspace_shell.py").read_text(encoding="utf-8")
    assert 'state["active_organization_id"] =' not in source
    assert 'state["active_facility_id"] =' not in source
    assert "render_access_context" in source


def test_flat_shell_hides_only_duplicate_buyer_navigation_controls():
    source = Path("modules/navigation/workspace_shell.py").read_text(encoding="utf-8")
    assert ".st-key-buyer_section_group" in source
    assert ".st-key-buyer_section" in source
    assert ".st-key-dev_org_context" not in source
    assert ".st-key-facility_context" not in source
