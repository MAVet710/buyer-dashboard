from scripts.seed_cowboy_kush_catalog import CATALOG, FLOWER_IMAGE, PREROLL_IMAGE


def test_cowboy_kush_catalog_has_25_unique_wholesale_finished_goods():
    assert len(CATALOG) == 25
    assert len({item.sku for item in CATALOG}) == 25
    assert sum(item.category == "Flower" for item in CATALOG) == 15
    assert sum(item.category == "Pre-Rolls" for item in CATALOG) == 10
    assert all(item.product_format and item.strain and item.image_url for item in CATALOG)


def test_cowboy_kush_catalog_uses_real_supplied_assets():
    assert {item.image_url for item in CATALOG} == {FLOWER_IMAGE, PREROLL_IMAGE}
    assert FLOWER_IMAGE.endswith("/prepacked-flower.png")
    assert PREROLL_IMAGE.endswith("/pre-roll.png")
