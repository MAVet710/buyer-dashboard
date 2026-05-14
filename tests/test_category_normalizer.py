from services.category_normalizer import normalize_competitor_category


def test_category_normalization_examples():
    cases = [
        ("Blue River Live Rosin 1g", "Concentrates", "Live Rosin"),
        ("Live Resin Cartridge 1g", "Vapes", "Live Resin Cartridge"),
        ("Liquid Live Resin All-In-One Vape", "Vapes", "Disposable"),
        ("Hash Infused Pre-Roll 1g", "Pre-Rolls", "Infused Pre-Roll"),
        ("Rosin Gummies 100mg", "Edibles", "Gummies"),
        ("Afghani Kush 14g Bulk Flower", "Flower", "Bulk Flower"),
        ("Blueberry 3.5g Flower", "Flower", "Whole Flower"),
        ("THCA Diamonds and Sauce", "Concentrates", "Sauce"),
        ("CBD Lotion 1:1", "Topicals", "Lotion"),
        ("RSO Syringe", "Concentrates", "RSO"),
    ]
    for name, cat, sub in cases:
        out = normalize_competitor_category(product_name=name)
        assert out["category"] == cat
        assert out["subcategory"] == sub


def test_page_category_fallback_uses_subtype():
    out = normalize_competitor_category(product_name="Shatter", page_category="Concentrates")
    assert out["category"] == "Concentrates"
    assert out["subcategory"] == "Shatter"
