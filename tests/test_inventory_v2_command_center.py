from pathlib import Path

import pandas as pd
import pytest

from modules.inventory_command_center import (
    apply_inventory_filters,
    build_retail_inventory_table,
)
from modules.inventory_receiving import (
    apply_receipt_to_inventory,
    build_sandbox_inbound_queue,
    normalize_metrc_packages,
    normalize_metrc_transfers,
    prepare_receipt_editor,
    validate_receipt_editor,
)
from modules.navigation.operation_context_bar import (
    PRODUCTION_OPERATION,
    RETAIL_OPERATION,
    available_operation_modes,
)
from modules.navigation.workspace_shell import (
    LOCATION_SETTINGS_SURFACE,
    _apply_secondary_choice,
    _available_flat_categories,
    _categories_for_operation,
    _default_route_for_category,
    _secondary_choices,
)
from services.workspace_navigation import (
    BUYER_WORKSPACE,
    COMAN_WORKSPACE,
    DATA_HUB_WORKSPACE,
    DATA_OPERATIONS,
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
    categories = [
        "Home",
        "Inventory",
        "Purchasing",
        "Orders",
        "Production",
        "Reports",
        "Compliance",
        "Data & Settings",
    ]

    retail = _categories_for_operation(categories, RETAIL_OPERATION)
    production = _categories_for_operation(categories, PRODUCTION_OPERATION)

    assert "Purchasing" in retail
    assert "Production" not in retail
    assert "Production" in production
    assert "Purchasing" not in production
    assert "Inventory" in both


def test_production_only_role_gets_first_class_inventory_route():
    groups = {HOME_OPS: [HOME_WORKSPACE], PRODUCTION_OPS: [COMAN_WORKSPACE]}
    categories = _available_flat_categories(groups, {})
    assert "Inventory" in categories
    assert "Production" in categories

    state = {
        "active_operation_mode": PRODUCTION_OPERATION,
        "operations_group": PRODUCTION_OPS,
        "workspace_mode": COMAN_WORKSPACE,
    }
    _default_route_for_category(state, "Inventory", groups, {})
    assert state["operations_group"] == PRODUCTION_OPS
    assert state["workspace_mode"] == COMAN_WORKSPACE


def test_location_settings_is_a_real_data_and_settings_surface():
    groups = {
        HOME_OPS: [HOME_WORKSPACE],
        RETAIL_OPS: [BUYER_WORKSPACE],
        DATA_OPERATIONS: [DATA_HUB_WORKSPACE],
    }
    choices = _secondary_choices(
        "Data & Settings",
        groups,
        {},
        operation_mode=RETAIL_OPERATION,
    )
    assert ("Location", "virtual", LOCATION_SETTINGS_SURFACE) in choices

    state = {"workspace_mode": DATA_HUB_WORKSPACE}
    _apply_secondary_choice(state, "Location", choices, {})
    assert state["flat_virtual_surface"] == LOCATION_SETTINGS_SURFACE

    _apply_secondary_choice(state, "Imports & Data", choices, {})
    assert "flat_virtual_surface" not in state
    assert state["workspace_mode"] == DATA_HUB_WORKSPACE


def test_inventory_v2_intercepts_only_primary_retail_or_production_inventory_surface():
    shell = (ROOT / "modules" / "navigation" / "workspace_shell.py").read_text(encoding="utf-8")

    assert 'INVENTORY_DASHBOARD_SECTION = "📊 Inventory Dashboard"' in shell
    assert 'str(state.get("buyer_section") or "") == INVENTORY_DASHBOARD_SECTION' in shell
    assert 'production_inventory = operation_mode == PRODUCTION_OPERATION and category == "Inventory"' in shell
    assert "render_inventory_command_center(state, operation_mode=operation_mode)" in shell
    assert "st.stop()" in shell
    assert "Inventory Audits" not in shell


def test_package_studio_accepts_inventory_prefill_without_renaming_workflows():
    studio = (ROOT / "modules" / "package_studio" / "ui.py").read_text(encoding="utf-8")

    assert 'state.pop("package_studio_prefill_lot_id", "")' in studio
    assert 'state.pop("package_studio_prefill_action", "")' in studio
    for label in (
        "Breakdown",
        "Pack Down",
        "Build Run",
        "Multi-Build",
        "Sample Pull",
        "Source Correction",
    ):
        assert label in studio


def test_sandbox_manifest_becomes_a_pending_receipt_with_new_package_tags():
    state = {
        "delivery_manifest_df": pd.DataFrame(
            [
                {
                    "Manifest #": "MAN-100",
                    "Vendor": "Atlantic Cultivation",
                    "Product": "Blue Dream 3.5g",
                    "Received Qty": 24,
                    "Package ID": "EXISTING-001",
                    "SKU": "BD35",
                    "COA ID": "COA-1",
                    "Unit Cost": 10.0,
                },
                {
                    "Manifest #": "MAN-100",
                    "Vendor": "Atlantic Cultivation",
                    "Product": "Orchard Haze Vape 1g",
                    "Received Qty": 12,
                    "Package ID": "EXISTING-002",
                    "SKU": "OHV1",
                    "COA ID": "COA-2",
                    "Unit Cost": 18.0,
                },
            ]
        )
    }

    queue, packages = build_sandbox_inbound_queue(state)
    assert len(queue) == 1
    assert queue.iloc[0]["Manifest"] == "MAN-100-PENDING"
    assert queue.iloc[0]["Package Count"] == 2
    assert queue.iloc[0]["Source"] == "Sandbox"
    pending = packages["MAN-100-PENDING"]
    assert len(pending) == 2
    assert pending["Package ID"].str.startswith("SBX-IN-").all()
    assert not set(pending["Package ID"]).intersection({"EXISTING-001", "EXISTING-002"})
    assert set(pending["Shipment State"]) == {"Accepted"}
    assert set(pending["Lab Testing State"]) == {"TestPassed"}


def _receiving_packages() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Incoming Item": "Blue Dream Bulk",
                "Package ID": "IN-001",
                "Traceability Package ID": "501",
                "Traceability Item ID": "101",
                "Quantity": 24,
                "Unit": "Each",
                "Shipment State": "Accepted",
                "Lab Testing State": "TestPassed",
                "Category": "Flower",
                "Vendor": "Atlantic Cultivation",
                "SKU": "",
                "COA ID": "COA-1",
                "Unit Cost": 0.0,
                "Retail Price": 0.0,
                "Expiration Date": "",
            },
            {
                "Incoming Item": "Unknown New Product",
                "Package ID": "IN-002",
                "Traceability Package ID": "502",
                "Traceability Item ID": "202",
                "Quantity": 12,
                "Unit": "Each",
                "Shipment State": "Accepted",
                "Lab Testing State": "TestPassed",
                "Category": "Vape",
                "Vendor": "Atlantic Cultivation",
                "SKU": "",
                "COA ID": "COA-2",
                "Unit Cost": 0.0,
                "Retail Price": 0.0,
                "Expiration Date": "",
            },
        ]
    )


def _receiving_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Product Name": "Blue Dream 3.5g",
                "SKU": "BD35",
                "Category": "Flower",
                "Unit Cost": 10.0,
                "Retail Price": 20.0,
            }
        ]
    )


def test_receive_auto_map_is_disabled_by_default_and_never_guesses_by_name():
    editor = prepare_receipt_editor(
        _receiving_packages(),
        _receiving_catalog(),
        default_room="Receiving",
    )
    assert editor["Mapped Product"].eq("").all()
    issues = validate_receipt_editor(editor, require_traceability_acceptance=True)
    assert any("Catalog product" in issue for issue in issues)


def test_receive_auto_map_reuses_only_prior_approved_location_mapping():
    history = {
        "metrc|item:101": {
            "catalog_product": "Blue Dream 3.5g",
            "catalog_sku": "BD35",
        }
    }
    editor = prepare_receipt_editor(
        _receiving_packages(),
        _receiving_catalog(),
        default_room="Vault",
        auto_map_history=True,
        mapping_history=history,
        source="Metrc",
    )
    assert editor.iloc[0]["Mapped Product"] == "Blue Dream 3.5g"
    assert editor.iloc[0]["Mapped SKU"] == "BD35"
    assert editor.iloc[0]["Room"] == "Vault"
    assert editor.iloc[1]["Mapped Product"] == ""


def test_metrc_receipt_requires_package_accepted_in_traceability():
    editor = pd.DataFrame(
        [
            {
                "Mapped Product": "Blue Dream 3.5g",
                "Room": "Vault",
                "Quantity": 24,
                "Package ID": "IN-001",
                "Shipment State": "Shipped",
            }
        ]
    )
    issues = validate_receipt_editor(editor, require_traceability_acceptance=True)
    assert any("accepted" in issue.casefold() for issue in issues)


def test_receipt_posts_new_package_without_overwriting_existing_inventory():
    current = _retail_state()["active_inventory_df"]
    editor = pd.DataFrame(
        [
            {
                "Incoming Item": "Blue Dream Bulk",
                "Mapped Product": "Blue Dream 3.5g",
                "Mapped SKU": "BD35",
                "Mapped Category": "Flower",
                "Package ID": "IN-NEW",
                "Traceability Package ID": "999",
                "Traceability Item ID": "101",
                "Vendor": "Atlantic Cultivation",
                "Room": "Vault",
                "Quantity": 24,
                "Unit": "Each",
                "Unit Cost": 10.0,
                "Retail Price": 20.0,
                "Expiration Date": "2027-08-19",
                "COA ID": "COA-NEW",
                "Lab Testing State": "TestPassed",
                "Lab Results": "Passed · 4 result(s)",
                "Shipment State": "Accepted",
            }
        ]
    )

    updated = apply_receipt_to_inventory(current, editor, manifest="MAN-200", source="Metrc")
    assert len(updated) == len(current) + 1
    received = updated.loc[updated["Package ID"] == "IN-NEW"].iloc[0]
    assert received["Product Name"] == "Blue Dream 3.5g"
    assert received["On Hand"] == 24
    assert received["Status"] == "Available"
    assert received["Traceability Manifest"] == "MAN-200"
    assert received["Traceability Source"] == "Metrc"
    assert received["Traceability Incoming Item"] == "Blue Dream Bulk"
    assert received["Traceability Item ID"] == "101"
    assert received["Traceability Package Record ID"] == "999"
    assert received["Lab Result Summary"] == "Passed · 4 result(s)"

    duplicate_editor = editor.copy()
    duplicate_editor.loc[0, "Package ID"] = "PKG-A1"
    with pytest.raises(ValueError, match="already exists"):
        apply_receipt_to_inventory(current, duplicate_editor, manifest="MAN-201", source="Metrc")


def test_unpassed_lab_state_posts_inventory_on_hold_not_available():
    current = _retail_state()["active_inventory_df"]
    editor = pd.DataFrame(
        [
            {
                "Incoming Item": "Pending Test Flower",
                "Mapped Product": "Blue Dream 3.5g",
                "Mapped SKU": "BD35",
                "Mapped Category": "Flower",
                "Package ID": "IN-HOLD",
                "Vendor": "Atlantic Cultivation",
                "Room": "Quarantine",
                "Quantity": 5,
                "Unit": "Each",
                "Unit Cost": 10.0,
                "Retail Price": 20.0,
                "Lab Testing State": "TestingInProgress",
                "Shipment State": "Accepted",
            }
        ]
    )
    updated = apply_receipt_to_inventory(current, editor, manifest="MAN-HOLD", source="Metrc")
    assert updated.loc[updated["Package ID"] == "IN-HOLD", "Status"].iloc[0] == "Hold"


def test_metrc_normalizers_keep_ids_needed_for_receive_details_and_lab_lookup():
    transfers = normalize_metrc_transfers(
        [
            {
                "Id": 42,
                "DeliveryId": 77,
                "ManifestNumber": "M-42",
                "ShipperFacilityName": "Vendor A",
                "PackageCount": 2,
                "ReceivedPackageCount": 1,
                "EstimatedArrivalDateTime": "2026-08-19T10:00:00",
            }
        ]
    )
    assert transfers.iloc[0]["Transfer ID"] == "42"
    assert transfers.iloc[0]["Manifest"] == "M-42"
    assert transfers.iloc[0]["Package Count"] == 2

    packages = normalize_metrc_packages(
        [
            {
                "PackageId": 501,
                "ItemId": 101,
                "ItemName": "Blue Dream Bulk",
                "PackageLabel": "1A406TEST",
                "ItemCategoryName": "Flower",
                "LabTestingState": "TestPassed",
                "ShipmentPackageState": "Accepted",
                "ShippedQuantity": 24,
                "ShippedUnitOfMeasureName": "Each",
            }
        ],
        vendor="Vendor A",
    )
    assert packages.iloc[0]["Package ID"] == "1A406TEST"
    assert packages.iloc[0]["Traceability Package ID"] == "501"
    assert packages.iloc[0]["Traceability Item ID"] == "101"
    assert packages.iloc[0]["Shipment State"] == "Accepted"
    assert packages.iloc[0]["Lab Testing State"] == "TestPassed"
    assert packages.iloc[0]["Quantity"] == 24


def test_receive_ui_is_a_popout_queue_then_receive_details_flow():
    source = (ROOT / "modules" / "inventory_receiving.py").read_text(encoding="utf-8")
    assert '@st.dialog("Receive inventory", width="large")' in source
    assert 'selection_mode="single-row"' in source
    assert "Click an inbound order to open Receive Details." in source
    assert "### Receive Details" in source
    assert '"Catalog product *"' in source
    assert '"Received qty *"' in source
    assert '"Room *"' in source
    assert '"Get Metrc Lab Results"' in source
    assert "Auto-map products during receive" in source
