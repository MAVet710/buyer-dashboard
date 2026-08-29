from __future__ import annotations

from scripts.seed_cowboy_kush_ma_coa_demo import BATCHES


def test_demo_coas_are_https_open_coa_passed_batch_inputs():
    assert len(BATCHES) >= 10
    assert len({batch.lot_code for batch in BATCHES}) == len(BATCHES)
    assert all(batch.coa_url.startswith("https://opencoa.org/coa/") for batch in BATCHES)
    assert all(batch.quantity > 0 for batch in BATCHES)
    assert all(0 <= batch.thca_percent <= 100 for batch in BATCHES)
    assert all(0 <= batch.tac_percent <= 100 for batch in BATCHES)
    assert all(0 <= batch.terpenes_percent <= 100 for batch in BATCHES)


def test_demo_seed_exercises_multiple_batches_for_one_storefront_product():
    wedding_cake = [batch for batch in BATCHES if batch.sku == "CBK-FLR-WEDDING-CAKE-35G"]
    assert len(wedding_cake) >= 2
    assert len({batch.coa_url for batch in wedding_cake}) == len(wedding_cake)


def test_retail_ready_demo_batches_match_existing_cowboy_kush_flower_sku_shape():
    retail_ready = [batch for batch in BATCHES if not batch.bulk]
    assert retail_ready
    assert all(batch.sku.startswith("CBK-FLR-") and batch.sku.endswith("-35G") for batch in retail_ready)


def test_bulk_demo_inventory_contains_high_terp_and_high_potency_flower():
    bulk = [batch for batch in BATCHES if batch.bulk]
    assert len(bulk) >= 4
    assert all(batch.sku.startswith("CBK-BULK-") for batch in bulk)
    assert all(batch.base_unit == "g" for batch in bulk)
    assert all(batch.category == "Bulk Flower" for batch in bulk)
    assert max(batch.terpenes_percent for batch in bulk) >= 4.0
    assert max(batch.thca_percent for batch in bulk) >= 31.0
    assert any(batch.strain == "Permanent Marker" and batch.terpenes_percent == 4.20 for batch in bulk)
    assert any(batch.strain == "Gelato Sunrise" and batch.terpenes_percent == 3.40 for batch in bulk)
    assert any(batch.strain == "Motorbreath" and batch.thca_percent == 31.44 and batch.terpenes_percent == 3.79 for batch in bulk)
