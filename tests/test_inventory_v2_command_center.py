from pathlib import Path

import pandas as pd

from modules.inventory_command_center import (
    apply_inventory_filters,
    build_retail_inventory_table,
)
from modules.navigation.operation_context_bar import (
    PRODUCTION_OPERATION,
    RETAIL_OPERATION,
    available_operation_modes,
)
from modules.navigation.workspace_shell import _categories_for_operation
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    HOME_OPS,
    HOME_WORKSPACE,
    PRODUCTION_OPS,
    RETAIL_OPS,
)


ROOT = Path(__file__).resolve().parents[1]


def _retail_state() -> dict:
    inventory = pd.DataFrame(
        [
            {
                "Product Name": "Blue Dream 3.5g",
                "SKU": "BD35",
                "Package ID": "PKG-A1",
                "Vendor": "Demo State Labs",
                "Room": "Sales Floor",
                "Category": "Flower",
                "Status": "Available",
                "On Hand": 5,
                "Reserved": 1,
                "Unit Cost": 10,
                "Retail Price": 20,
                "Received Date": "2026-06-01",
            },
            {
                "Product Name": "Blue Dream 3.5g",
                "SKU": "BD35",
                "Package ID": "PKG-A2",
                "Vendor": "Demo State Labs",
                "Room": "Sales Floor",
                "Category": "Flower",
                "Status": "Available",
                "On Hand": 5,
                "Reserved": 0,
                "Unit Cost": 10,
                "Retail Price": 20,
                "Received Date": "2026-06-15",
            },
            {
                "Product Name": "Orchard Haze Vape 1g",
                "SKU": "OHV1",
                "Package ID": "PKG-B1",
                "Vendor": "North Shore",
                "Room": "Vault",
                "Category": "Vape",
                "Status": "Available",
                "On Hand": 2,
                "Reserved": 0,
                "Unit Cost": 18,
                "Retail Price": 40,
                "Received Date": "2026-08-01",
            },
        ]
    )
    sales = pd.DataFrame(
        [
            {
                "Product Name": "Blue Dream 3.5g",
                "Quantity Sold": 30,
                "Report Start": "2026-07-21",
                "Report End": "2026-08-19",
            },
            {
                "Product Name": "Orchard Haze Vape 1g",
                "Quantity Sold": 20,
                "Report Start": "2026-07-21",
                "Report End": "2026-08-19",
            },
        ]
    )
    return {"active_inventory_df": inventory, "active_sales_df": sales}


def test_retail_inventory_products_are_aggregated_with_velocity_and_margin():
    frame = build_retail_inventory_table(_retail_state(), grain="Products")

    assert set(frame["Product"]) == {"Blue Dream 3.5g", "Orchard Haze Vape 1g"}
    blue = frame.loc[frame["Product"] == "Blue Dream 3.5g"].iloc[0]
    orchard = frame.loc[frame["Product"] == "Orchard Haze Vape 1g"].iloc[0]

    assert blue["Available"] == 10
    assert blue["Reserved"] == 1
    assert round(float(blue["30d Sold"]), 2) == 30.0
    assert round(float(blue["DOH"]), 2) == 10.0
    assert round(float(blue["Margin"]), 2) == 50.0

    assert orchard["Available"] == 2
    assert round(float(orchard["DOH"]), 2) == 3.0
    assert orchard["Attention"] == "Reorder now"


def test_retail_inventory_package_grain_preserves_package_rows():
    frame = build_retail_inventory_table(_retail_state(), grain="Packages")

    assert len(frame) == 3
    assert set(frame["Package ID"]) == {"PKG-A1", "PKG-A2", "PKG-B1"}
    assert frame.loc[frame["Package ID"] == "PKG-A1", "Product"].iloc[0] == "Blue Dream 3.5g"


def test_inventory_saved_views_and_search_are_operational_filters():
    frame = build_retail_inventory_table(_retail_state(), grain="Products")

    low = apply_inventory_filters(frame, saved_view="Low Stock")
    assert list(low["Product"]) == ["Orchard Haze Vape 1g"]

    vendor = apply_inventory_filters(frame, search="demo state", saved_view="All Inventory")
    assert list(vendor["Product"]) == ["Blue Dream 3.5g"]

    room = apply_inventory_filters(frame, room="Vault")
    assert list(room["Product"]) == ["Orchard Haze Vape 1g"]


def test_operation_selector_only_exposes_modes_the_role_can_use():
    groups = {
        HOME_OPS: [HOME_WORKSPACE],
        RETAIL_OPS: [BUYER_WORKSPACE],
        PRODUCTION_OPS: [COMAN_WORKSPACE],
    }

    assert available_operation_modes(groups, {"auth_user_role": "dev"}) == [
        RETAIL_OPERATION,
        PRODUCTION_OPERATION,
    ]
    assert available_operation_modes(groups, {"auth_user_role": "buyer"}) == [RETAIL_OPERATION]
    assert available_operation_modes(groups, {"auth_user_role": "planner"}) == [PRODUCTION_OPERATION]


def test_operation_mode_changes_the_flat_navigation_surface():
    categories = ["Home", "Inventory", "Purchasing", "Orders", "Production", "Reports", "Compliance", "Data & Settings"]

    retail = _categories_for_operation(categories, RETAIL_OPERATION)
    production = _categories_for_operation(categories, PRODUCTION_OPERATION)

    assert "Purchasing" in retail
    assert "Production" not in retail
    assert "Production" in production
    assert "Purchasing" not in production
    assert "Inventory" in both


def test_inventory_v2_intercepts_only_primary_inventory_dashboard():
    shell = (ROOT / "modules" / "navigation" / "workspace_shell.py").read_text(encoding="utf-8")

    assert 'INVENTORY_DASHBOARD_SECTION = "📊 Inventory Dashboard"' in shell
    assert 'str(state.get("buyer_section") or "") == INVENTORY_DASHBOARD_SECTION' in shell
    assert "render_inventory_command_center(state, operation_mode=operation_mode)" in shell
    assert "st.stop()" in shell
    assert "Inventory Audits" not in shell  # audits remain routed by their existing section identifiers


def test_package_studio_accepts_inventory_prefill_without_renaming_workflows():
    studio = (ROOT / "modules" / "package_studio" / "ui.py").read_text(encoding="utf-8")

    assert 'state.pop("package_studio_prefill_lot_id", "")' in studio
    assert 'state.pop("package_studio_prefill_action", "")' in studio
    for label in ("Breakdown", "Pack Down", "Build Run", "Multi-Build", "Sample Pull", "Source Correction"):
        assert label in studio
