from pathlib import Path

from modules.extraction.inventory_eligibility import classify_extraction_inventory


ROOT = Path(__file__).resolve().parents[1]


def classify(**overrides):
    values = {
        "item_type": "cannabis",
        "product_name": "GMO Bulk Flower",
        "sku": "GMO",
        "base_unit": "g",
        "category": "Bulk Flower",
        "subcategory": "",
        "product_format": "Bulk",
    }
    values.update(overrides)
    return classify_extraction_inventory(**values)


def test_source_material_and_extraction_wip_are_eligible():
    assert classify().eligible
    assert classify().role == "source_material"

    for name in ("Fresh Frozen GMO", "Trim - Blue Dream", "Biomass", "Dry Sift", "Kief"):
        result = classify(product_name=name, category=name, product_format="Bulk")
        assert result.eligible, name
        assert result.role == "source_material"

    for name in ("Winterized Crude", "Decarbed Oil", "Distillate WIP", "Live Resin WIP", "Rosin WIP"):
        result = classify(item_type="wip", product_name=name, category="WIP", product_format="Intermediate")
        assert result.eligible, name
        assert result.role == "extraction_wip"


def test_explicit_bulk_extraction_output_can_remain_visible():
    result = classify(
        item_type="finished_good",
        product_name="Bulk Distillate",
        category="Concentrate",
        product_format="Bulk",
    )
    assert result.eligible
    assert result.role == "bulk_output"


def test_consumer_ready_and_unrelated_items_are_excluded():
    cases = [
        dict(item_type="cannabis", product_name="GMO Pre-Roll 1g", category="Pre-Roll", product_format="1g"),
        dict(item_type="cannabis", product_name="GMO Flower", category="Flower", product_format="3.5g"),
        dict(item_type="cannabis", product_name="GMO Packaged Flower", category="Flower", product_format="3.5g"),
        dict(item_type="finished_good", product_name="Live Resin 1g", category="Concentrate", product_format="1g Jar"),
        dict(item_type="finished_good", product_name="Blue Dream Vape Cartridge", category="Vape", product_format="Cartridge"),
        dict(item_type="finished_good", product_name="Strawberry Gummies", category="Edible", product_format="Gummy"),
        dict(item_type="packaging", product_name="1g Concentrate Jar", category="Packaging", product_format="Jar"),
    ]
    for row in cases:
        result = classify(**row)
        assert not result.eligible, row


def test_extraction_inventory_ui_uses_filtered_projection_without_broad_fallback():
    source = (ROOT / "frontend/src/pages/ExtractionUnifiedPage.tsx").read_text()
    assert "/api/v1/extraction-inventory/lots" in source
    assert "extraction-production-inventory-fallback" not in source
    assert "View all Production Inventory" in source
    assert "Source material" in source
    assert "Extraction WIP" in source
    assert "Bulk outputs" in source


def test_legacy_extraction_lot_reads_are_projected_for_all_frontend_surfaces():
    source = (ROOT / "frontend/src/lib/api.ts").read_text()
    assert 'path === "/api/v1/extraction/lots"' in source
    assert '"/api/v1/extraction-inventory/lots"' in source
