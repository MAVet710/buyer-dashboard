from pathlib import Path

import pandas as pd

from modules.inventory_command_center import (
    PRODUCTION_BUILTIN_VIEWS,
    _is_cultivation_facility,
    apply_inventory_filters,
)


ROOT = Path(__file__).resolve().parents[1]


def _production_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SKU": "BULK-FLOWER",
                "Product": "Blue Dream Bulk Flower",
                "Material Type": "Cannabis Flower",
                "Source / Supplier": "Cultivation A",
                "External Package ID": "1A4FF030000001",
                "Room": "VAULT-A",
                "Status": "Available",
                "Available": 4200.0,
                "Unit": "g",
                "Attention": "Production ready",
            },
            {
                "SKU": "TRIM-001",
                "Product": "Blue Dream Trim",
                "Material Type": "Biomass Trim",
                "Source / Supplier": "Cultivation A",
                "External Package ID": "1A4FF030000002",
                "Room": "INPUT",
                "Status": "Available",
                "Available": 8.0,
                "Unit": "kg",
                "Attention": "Production ready",
            },
            {
                "SKU": "WIP-CRUDE",
                "Product": "Blue Dream Crude",
                "Material Type": "WIP Crude Oil",
                "Source / Supplier": "",
                "External Package ID": "1A4FF030000003",
                "Room": "PROCESSING",
                "Status": "Available",
                "Available": 1200.0,
                "Unit": "g",
                "Attention": "Production ready",
            },
        ]
    )


def test_production_views_do_not_reuse_retail_doh_views():
    assert "All Material" in PRODUCTION_BUILTIN_VIEWS
    assert "Production Ready" in PRODUCTION_BUILTIN_VIEWS
    assert "WIP" in PRODUCTION_BUILTIN_VIEWS
    assert "Under 14 DOH" not in PRODUCTION_BUILTIN_VIEWS
    assert "Slow Movers" not in PRODUCTION_BUILTIN_VIEWS


def test_production_material_filters_use_material_semantics():
    frame = _production_frame()

    bulk = apply_inventory_filters(frame, saved_view="Bulk Flower")
    assert list(bulk["Product"]) == ["Blue Dream Bulk Flower"]

    trim = apply_inventory_filters(frame, saved_view="Biomass / Trim")
    assert list(trim["Product"]) == ["Blue Dream Trim"]

    wip = apply_inventory_filters(frame, saved_view="WIP")
    assert list(wip["Product"]) == ["Blue Dream Crude"]

    low = apply_inventory_filters(frame, saved_view="Low Balance")
    assert list(low["Product"]) == ["Blue Dream Trim"]


def test_production_search_can_find_source_supplier_and_package():
    frame = _production_frame()
    source = apply_inventory_filters(frame, search="Cultivation A", saved_view="All Material")
    assert set(source["Product"]) == {"Blue Dream Bulk Flower", "Blue Dream Trim"}

    package = apply_inventory_filters(frame, search="000003", saved_view="All Material")
    assert list(package["Product"]) == ["Blue Dream Crude"]


def test_cultivation_facility_exposes_plant_grain_signal():
    assert _is_cultivation_facility({"active_license_type": "Marijuana Cultivator"}) is True
    assert _is_cultivation_facility({"active_facility_type": "Manufacturing"}) is False


def test_production_receiving_is_not_retail_inventory_receiving():
    command_center = (ROOT / "modules" / "inventory_command_center.py").read_text(encoding="utf-8")
    production_receiving = (ROOT / "modules" / "production_inventory_receiving.py").read_text(encoding="utf-8")

    assert 'disabled=is_production' not in command_center
    assert "render_production_receive_inventory_dialog" in command_center
    assert 'transaction_type="receive"' in production_receiving
    assert "facility_id=facility_id" in production_receiving
    assert "Retail inventory is never modified" in production_receiving
