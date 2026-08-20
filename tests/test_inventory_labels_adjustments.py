from pathlib import Path

import pandas as pd

import modules.inventory_adjustments as adjustments
from modules.inventory_labels import InventoryLabel, build_label_pdf, build_label_records, build_print_html
from services import metrc_inventory_adjustments as metrc_adjustments


def test_label_records_use_product_external_package_and_minimal_location_header():
    state = {
        "active_organization_name": "DEV Sandbox",
        "active_facility_name": "Sandbox Facility",
        "demo_company_profile": {"license_number": "SANDBOX-MA-DEMO"},
    }
    rows = pd.DataFrame(
        [
            {
                "Product": "Blue Dream Flower 3.5g",
                "External Package ID": "1A4060300000000000000123",
            }
        ]
    )
    labels = build_label_records(state, rows)
    assert labels == [
        InventoryLabel(
            product_name="Blue Dream Flower 3.5g",
            external_package_id="1A4060300000000000000123",
            facility_name="Sandbox Facility",
            organization_name="DEV Sandbox",
            license_number="SANDBOX-MA-DEMO",
        )
    ]


def test_label_output_is_printable_and_omits_contact_fields():
    labels = [
        InventoryLabel(
            product_name="Blue Dream Flower 3.5g",
            external_package_id="1A4060300000000000000123",
            facility_name="Sandbox Facility",
            license_number="MR123456",
        )
    ]
    pdf = build_label_pdf(labels)
    html = build_print_html(labels)
    assert pdf.startswith(b"%PDF")
    assert "Blue Dream Flower 3.5g" in html
    assert "1A4060300000000000000123" in html
    assert "License #MR123456" in html
    assert "window.print()" in html
    lowered = html.casefold()
    assert "phone" not in lowered
    assert "email" not in lowered
    assert "website" not in lowered
    assert "address" not in lowered


def test_metrc_units_are_normalized_for_package_adjustments():
    assert metrc_adjustments.normalize_metrc_unit("g") == "Grams"
    assert metrc_adjustments.normalize_metrc_unit("oz") == "Ounces"
    assert metrc_adjustments.normalize_metrc_unit("unit") == "Each"


def test_metrc_incremental_uses_post_and_absolute_uses_put(monkeypatch):
    captured = []

    def fake_request(method, **kwargs):
        captured.append((method, kwargs))
        return {"ok": True}

    monkeypatch.setattr(metrc_adjustments, "_request", fake_request)
    common = dict(
        state="MA",
        user_api_key="user",
        integrator_api_key="integrator",
        license_number="MR123",
        package_label="1A4060300000000000000123",
        unit="g",
        reason="Scale Variance",
    )
    metrc_adjustments.submit_package_adjustment(
        adjustment_type="incremental", quantity=-2.0, **common
    )
    metrc_adjustments.submit_package_adjustment(
        adjustment_type="absolute", quantity=100.0, **common
    )
    assert captured[0][0] == "POST"
    assert captured[0][1]["json_payload"][0]["Quantity"] == -2.0
    assert captured[1][0] == "PUT"
    assert captured[1][1]["json_payload"][0]["Quantity"] == 100.0


def test_adjustment_roles_are_restricted():
    assert adjustments.can_adjust_inventory({"auth_user_role": "admin"}) is True
    assert adjustments.can_adjust_inventory({"auth_user_role": "supervisor"}) is True
    assert adjustments.can_adjust_inventory({"auth_user_role": "operator"}) is True
    assert adjustments.can_adjust_inventory({"auth_user_role": "qa"}) is True
    assert adjustments.can_adjust_inventory({"auth_user_role": "buyer"}) is False
    assert adjustments.can_adjust_inventory({"auth_user_role": "read_only"}) is False


def test_retail_adjustment_calculates_incremental_and_absolute_without_metrc(monkeypatch):
    state = {"auth_user_role": "admin"}
    monkeypatch.setattr(
        adjustments,
        "_retail_current_and_row",
        lambda package_id: (pd.DataFrame(), 0, 10.0, 0.0, "unit"),
    )
    monkeypatch.setattr(
        adjustments,
        "_apply_retail_local",
        lambda state, package_id, final_quantity: (final_quantity - 10.0, "unit"),
    )
    monkeypatch.setattr(adjustments, "_append_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr(adjustments, "_credentials", lambda state: None)

    incremental = adjustments.apply_inventory_adjustment(
        state,
        operation_mode="Retail Ops",
        package_id="PKG-1",
        durable_lot_id="",
        adjustment_type="Incremental",
        entered_quantity=-2.0,
        reason="Inventory count correction",
        reason_note="",
        sync_to_metrc=False,
        bypass_state_system=False,
    )
    assert incremental["previous_quantity"] == 10.0
    assert incremental["delta"] == -2.0
    assert incremental["final_quantity"] == 8.0

    absolute = adjustments.apply_inventory_adjustment(
        state,
        operation_mode="Retail Ops",
        package_id="PKG-1",
        durable_lot_id="",
        adjustment_type="Set Quantity",
        entered_quantity=4.0,
        reason="Inventory count correction",
        reason_note="",
        sync_to_metrc=False,
        bypass_state_system=False,
    )
    assert absolute["delta"] == -6.0
    assert absolute["final_quantity"] == 4.0


def test_inventory_command_center_exposes_shared_label_and_adjust_actions():
    source = Path("modules/inventory_command_center.py").read_text(encoding="utf-8")
    assert '"External Package ID"' in source
    assert '"Print labels"' in source
    assert '"Adjust"' in source
    assert "open_inventory_label_dialog" in source
    assert "open_inventory_adjustment_dialog" in source
    assert "render_inventory_label_dialog" in source
    assert "render_inventory_adjustment_dialog" in source
