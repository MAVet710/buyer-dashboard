import pandas as pd

from services.buyer_intelligence_brief import (
    _is_data_specific,
    build_store_evidence_markdown,
)


def _product_rows():
    return pd.DataFrame(
        [
            {
                "product_name": "AMP Lilac Diesel Pre-Roll 1g (SH)",
                "category": "pre roll",
                "strain_type": "sativa hybrid",
                "package_size": "1g",
                "avg_daily_units": 2.0,
                "on_hand_units": 3.0,
                "units_sold": 60.0,
                "days_of_cover": 1.5,
                "risk_flag": "Reorder Risk",
            },
            {
                "product_name": "Slow Flower 3.5g",
                "category": "flower",
                "strain_type": "hybrid",
                "package_size": "3.5g",
                "avg_daily_units": 0.1,
                "on_hand_units": 20.0,
                "units_sold": 3.0,
                "days_of_cover": 200.0,
                "risk_flag": "Monitor",
            },
        ]
    )


def test_store_evidence_names_exact_actions_and_numbers():
    summary = {
        "tracked_skus": 2,
        "total_units_sold": 63,
        "total_revenue": 900,
        "at_risk_skus": 1,
    }
    categories = pd.DataFrame(
        [{"category": "pre roll", "units_sold": 60, "revenue": 800}]
    )

    markdown, datasets = build_store_evidence_markdown(
        summary, categories, _product_rows(), 30
    )

    assert "AMP Lilac Diesel Pre-Roll 1g (SH)" in markdown
    assert "3.0 on hand" in markdown
    assert "60 sold" in markdown
    assert "1.5 days cover" in markdown
    assert "Slow Flower 3.5g" in markdown
    assert "200.0 days cover" in markdown
    assert "purchase_priorities" in datasets
    assert "sku_risk" in datasets
    assert "overstock_watch" in datasets


def test_generic_ai_answer_is_rejected_when_store_anchors_exist():
    _, datasets = build_store_evidence_markdown(
        {"tracked_skus": 2, "total_units_sold": 63, "at_risk_skus": 1},
        pd.DataFrame([{"category": "pre roll", "units_sold": 60}]),
        _product_rows(),
        30,
    )

    assert _is_data_specific(
        "Close assortment gaps in top velocity categories before adding long-tail SKUs.",
        datasets,
    ) is False
    assert _is_data_specific(
        "Review AMP Lilac Diesel Pre-Roll 1g (SH) first because its cover is low.",
        datasets,
    ) is True


def test_confidence_is_not_high_without_inventory_evidence():
    products = _product_rows().copy()
    products["on_hand_units"] = pd.NA
    products["days_of_cover"] = pd.NA

    markdown, _ = build_store_evidence_markdown(
        {"tracked_skus": 2, "total_units_sold": 63, "at_risk_skus": 0},
        pd.DataFrame(),
        products,
        30,
    )

    assert "Data confidence: Low" in markdown
