import pandas as pd

from modules.navigation.product_360 import build_product_360_snapshot, stage_product_for_po


def _state():
    product = "Demo Labs Critical Kush Flower 3.5g"
    return product, {
        "active_inventory_df": pd.DataFrame(
            [
                {
                    "Product Name": product,
                    "SKU": "DL-CK-35",
                    "Brand": "Demo Labs",
                    "Vendor": "Demo Supply",
                    "Category": "Flower",
                    "On Hand": 4,
                    "Reserved": 1,
                    "Unit Cost": 16.0,
                    "Retail Price": 40.0,
                    "METRC Package ID": "1A406030000DECISION001",
                    "Room": "Sales Floor",
                    "Status": "Available",
                    "Received Date": "2026-07-01",
                    "Expiration Date": "2026-10-01",
                    "Lab Status": "Passed",
                }
            ]
        ),
        "active_sales_df": pd.DataFrame(
            [
                {"Product Name": product, "Quantity Sold": 10, "Order Time": "2026-06-22"},
                {"Product Name": product, "Quantity Sold": 20, "Order Time": "2026-07-22"},
                {"Product Name": product, "Quantity Sold": 14, "Order Time": "2026-08-14"},
                {"Product Name": product, "Quantity Sold": 6, "Order Time": "2026-08-20"},
            ]
        ),
    }


def test_product_360_decision_layer_connects_inventory_sales_packages_and_economics():
    product, state = _state()
    snapshot = build_product_360_snapshot(state, product)

    assert snapshot["sku"] == "DL-CK-35"
    assert snapshot["brand"] == "Demo Labs"
    assert snapshot["vendor"] == "Demo Supply"
    assert snapshot["reserved"] == 1
    assert snapshot["available_after_reserved"] == 3
    assert snapshot["package_count"] == 1
    assert snapshot["status"] == "Available"
    assert snapshot["lab_status"] == "Passed"
    assert snapshot["inventory_value"] == 64.0
    assert snapshot["retail_value"] == 160.0
    assert snapshot["units_sold_7d"] == 20.0
    assert snapshot["units_sold_30d"] == 40.0
    assert snapshot["units_sold_60d"] == 50.0
    assert snapshot["units_sold_90d"] == 50.0
    assert snapshot["target_units"] > 0
    assert snapshot["decision_signal"] == "ORDER NOW"
    assert snapshot["estimated_reorder_cost"] == snapshot["target_units"] * 16.0
    assert snapshot["estimated_reorder_gross_profit"] == snapshot["target_units"] * 24.0
    assert not snapshot["package_details"].empty


def test_product_360_po_action_upserts_same_product_when_recommendation_changes():
    product, state = _state()
    snapshot = build_product_360_snapshot(state, product)
    first = stage_product_for_po(state, snapshot)

    changed = dict(snapshot)
    changed["target_units"] = snapshot["target_units"] + 12
    changed["unit_cost"] = 15.5
    second = stage_product_for_po(state, changed)

    assert len(state["po_items"]) == 1
    assert first["Description"] == second["Description"]
    assert state["po_items"][0]["Quantity"] == changed["target_units"]
    assert state["po_items"][0]["Price"] == 15.5
    assert state["po_items"][0]["Total"] == changed["target_units"] * 15.5
