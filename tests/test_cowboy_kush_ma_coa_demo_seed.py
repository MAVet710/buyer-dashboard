from __future__ import annotations

from scripts.seed_cowboy_kush_ma_coa_demo import BATCHES


def test_demo_coas_are_https_open_coa_passed_batch_inputs():
    assert len(BATCHES) >= 5
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


def test_demo_seed_matches_existing_cowboy_kush_flower_sku_shape():
    assert all(batch.sku.startswith("CBK-FLR-") and batch.sku.endswith("-35G") for batch in BATCHES)
