from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from services.purchasing_context import prepare_purchasing_context, purchasing_frame


def _state() -> dict:
    inventory = pd.DataFrame(
        [
            {
                "SKU": "SBX-FLR-001",
                "Product Name": "Sandbox Blue Dream 3.5g",
                "Category": "Flower",
                "Brand": "Sandbox House",
                "Available": 12,
                "Cost": 11.0,
                "Med Price": 32.0,
                "Package Size": "3.5g",
                "EComm Strain Type": "Hybrid",
            },
            {
                "SKU": "SBX-VAP-001",
                "Product Name": "Sandbox Citrus Vape 1g",
                "Category": "Vape",
                "Brand": "Sandbox House",
                "Available": 4,
                "Cost": 18.0,
                "Med Price": 44.0,
                "Package Size": "1g",
                "EComm Strain Type": "Sativa Hybrid",
            },
        ]
    )
    sales = pd.DataFrame(
        [
            {"SKU": "SBX-FLR-001", "Quantity Sold": 60, "Net Sales": 1800.0, "Order Time": "2026-08-01"},
            {"SKU": "SBX-FLR-001", "Quantity Sold": 30, "Net Sales": 900.0, "Order Time": "2026-08-20"},
            {"SKU": "SBX-VAP-001", "Quantity Sold": 40, "Net Sales": 1600.0, "Order Time": "2026-08-01"},
            {"SKU": "SBX-VAP-001", "Quantity Sold": 20, "Net Sales": 800.0, "Order Time": "2026-08-20"},
        ]
    )
    return {
        "active_inventory_df": inventory,
        "active_sales_df": sales,
        "demo_budget_df": pd.DataFrame([{"Period": "August", "Budget": 25000, "Actual": 12000}]),
    }


def test_purchasing_auto_populates_from_active_app_data_without_inventory_prep():
    state = _state()
    assert "detail_product_cached_df" not in state

    report = prepare_purchasing_context(state)

    assert report["ready"] is True
    assert report["rows"] == 2
    assert not state["detail_cached_df"].empty
    assert not state["detail_product_cached_df"].empty
    assert not state["purchasing_ready_df"].empty
    assert not state["purchasing_budget_df"].empty
    assert state["purchasing_context_source"] == "active_app_data"
    assert set(state["purchasing_ready_df"]["sku"]) == {"SBX-FLR-001", "SBX-VAP-001"}


def test_purchasing_frame_self_prepares_when_opened_first():
    state = _state()
    frame = purchasing_frame(state)
    assert len(frame) == 2
    assert "reorderqty" in frame.columns
    assert "reorderpriority" in frame.columns


def test_purchasing_runtime_is_installed_after_sandbox_hydration():
    source = Path("streamlit_app.py").read_text(encoding="utf-8")
    sandbox = source.index("install_sandbox_market_hydration_runtime(st)")
    purchasing = source.index("install_purchasing_context_runtime()")
    assert sandbox < purchasing


def test_po_builder_no_longer_requires_inventory_prep():
    source = Path("views/po_builder_view.py").read_text(encoding="utf-8")
    smart = Path("views/po_builder_smart.py").read_text(encoding="utf-8")
    assert "Go to Inventory Prep first" not in source
    assert "purchasing_frame(st.session_state)" in source
    assert "purchasing_frame(st.session_state)" in smart


def test_inventory_stale_selected_rows_are_discarded_before_iloc():
    from modules import inventory_command_center as inventory
    from services.inventory_selection_guard import install_inventory_selection_guard

    install_inventory_selection_guard()
    inventory._inventory_rendered_row_count = 2
    event = SimpleNamespace(selection=SimpleNamespace(rows=[0, 5, -1, 1, 1]))

    assert inventory._selected_rows(event) == [0, 1]
