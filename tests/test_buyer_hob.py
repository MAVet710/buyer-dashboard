import pandas as pd
from services.buyer_hob import normalize_brand_name, classify_inventory, build_category_coverage, analyze_deals


def test_normalize_brand_name():
    assert normalize_brand_name(" Mindy’s ") == "mindys"
    assert normalize_brand_name("Mindys") == "mindys"
    assert normalize_brand_name("CRESCO") == "cresco"
    assert normalize_brand_name(None) == ""


def test_classify_inventory():
    df = pd.DataFrame({"Brand": ["Cresco", "Other", ""], "Qty": [10, 5, 2]})
    out = classify_inventory(df, ["Cresco"], qty_col="Qty", brand_col="Brand")
    assert list(out["brand_group"]) == ["HOB", "Third Party", "Unknown"]


def test_category_coverage():
    df = pd.DataFrame({"cat": ["Edibles", "Edibles"], "Qty": [2, 8], "brand_group": ["HOB", "Third Party"]})
    cov = build_category_coverage(df, "Qty", "cat")
    assert cov.iloc[0]["Coverage Status"] == "Critical Gap"


def test_deal_support_filtering_and_missing_brand_col():
    df = pd.DataFrame({"cat": ["Prerolls"], "Qty": [4], "price": [10], "name": ["500mg item"], "brand_group": ["HOB"]})
    deals = [{"name": "d1", "category": "Prerolls", "price_threshold": 12, "keyword": "500mg"}]
    out = analyze_deals(df, deals, "Qty", "cat", None, "price", "name")
    assert out.iloc[0]["Eligible Total Units"] == 4
