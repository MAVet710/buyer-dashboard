import pandas as pd

from views.buyer_perfect_view import _build_buyer_pipeline


def _sales_df():
    return pd.DataFrame(
        [
            {"Product Name": "Blue Dream Pre-Roll 1g", "Quantity Sold": 12, "Category": "Pre Rolls"},
            {"Product Name": "Mystery Item", "Quantity Sold": 3, "Category": "Flower"},
        ]
    )


def test_pipeline_derives_subcategory_without_raw_category_column():
    inv_raw = pd.DataFrame(
        [
            {"Name": "Blue Dream Pre-Roll 1g", "Med Total": 10},
            {"Name": "Northern Lights Vape 0.5g", "Med Total": 4},
        ]
    )

    detail, detail_product, inv_df, _ = _build_buyer_pipeline(
        inv_raw_df=inv_raw,
        sales_raw_df=_sales_df(),
        doh_threshold=21,
        velocity_adjustment=1.0,
        date_diff=30,
    )

    assert "subcategory" in inv_df.columns
    assert set(inv_df["subcategory"].tolist()) == {"pre rolls", "vapes"}
    assert "subcategory" in detail.columns
    assert "subcategory" in detail_product.columns


def test_pipeline_uses_itemname_alias_and_preserves_parsed_fields():
    inv_raw = pd.DataFrame(
        [
            {"SKU": "Sour Diesel Flower 3.5g", "On Hand": 7},
            {"SKU": "Unknown Label", "On Hand": 1},
        ]
    )

    _, _, inv_df, _ = _build_buyer_pipeline(
        inv_raw_df=inv_raw,
        sales_raw_df=_sales_df(),
        doh_threshold=21,
        velocity_adjustment=1.0,
        date_diff=30,
    )

    assert "itemname" in inv_df.columns
    assert inv_df.loc[0, "packagesize"] == "3.5g"
    assert inv_df.loc[0, "strain_type"] in {"sativa", "unspecified"}


def test_pipeline_partial_parse_keeps_derived_columns_present():
    inv_raw = pd.DataFrame(
        [
            {"Item": "Gelato Gummies 100mg", "Quantity": 8},
            {"Item": "Plain Product", "Quantity": 2},
        ]
    )

    _, _, inv_df, _ = _build_buyer_pipeline(
        inv_raw_df=inv_raw,
        sales_raw_df=_sales_df(),
        doh_threshold=21,
        velocity_adjustment=1.0,
        date_diff=30,
    )

    assert set(["subcategory", "packagesize", "strain_type"]).issubset(inv_df.columns)
    assert inv_df.loc[0, "packagesize"] == "100mg"
    assert inv_df.loc[1, "packagesize"] == "unknown"


def test_pipeline_parser_failures_use_safe_fallback_values():
    inv_raw = pd.DataFrame(
        [
            {"Product": "", "Qty": 5},
            {"Product": "   ", "Qty": 6},
        ]
    )

    _, _, inv_df, _ = _build_buyer_pipeline(
        inv_raw_df=inv_raw,
        sales_raw_df=_sales_df(),
        doh_threshold=21,
        velocity_adjustment=1.0,
        date_diff=30,
    )

    assert (inv_df["subcategory"] == "unspecified").all()
    assert (inv_df["packagesize"] == "unknown").all()
    assert (inv_df["strain_type"] == "unspecified").all()


def test_pipeline_normalizes_real_upload_headers_for_inventory_and_sales():
    inv_raw = pd.DataFrame(
        [
            {"Product": "Blue Dream Pre-Roll 1g", "Category": "Pre Rolls", "Available": 10},
            {"Product": "Northern Lights Vape 0.5g", "Category": "Vapes", "Available": 4},
        ]
    )
    sales_raw = pd.DataFrame(
        [
            {"Product Name": "Blue Dream Pre-Roll 1g", "Category": "Pre Rolls", "Total Inventory Sold": 12},
            {"Product Name": "Northern Lights Vape 0.5g", "Category": "Vapes", "Total Inventory Sold": 5},
        ]
    )

    detail, detail_product, inv_df, sales_detail_df = _build_buyer_pipeline(
        inv_raw_df=inv_raw,
        sales_raw_df=sales_raw,
        doh_threshold=21,
        velocity_adjustment=1.0,
        date_diff=30,
    )

    assert {"itemname", "subcategory", "onhandunits"}.issubset(inv_df.columns)
    assert {"product_name", "mastercategory", "unitssold"}.issubset(sales_detail_df.columns)
    assert "subcategory" in detail.columns
    assert "subcategory" in detail_product.columns
