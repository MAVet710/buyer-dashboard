import pandas as pd

from services.buyer_intelligence_brief import build_store_evidence_markdown


def test_buyer_intelligence_evidence_has_no_generic_source_or_rule_noise():
    products = pd.DataFrame(
        [
            {
                "product_name": "Example Pre-Roll 1g",
                "category": "pre roll",
                "strain_type": "hybrid",
                "package_size": "1g",
                "avg_daily_units": 2.0,
                "on_hand_units": 4.0,
                "units_sold": 60.0,
                "days_of_cover": 2.0,
                "risk_flag": "Reorder Risk",
            }
        ]
    )
    summary = {
        "tracked_skus": 1,
        "total_units_sold": 60,
        "total_revenue": 600,
        "at_risk_skus": 1,
    }
    categories = pd.DataFrame(
        [{"category": "pre roll", "units_sold": 60, "revenue": 600}]
    )

    brief, _ = build_store_evidence_markdown(summary, categories, products, 30)

    assert "Example Pre-Roll 1g" in brief
    assert "National Retail Federation" not in brief
    assert "Shopify" not in brief
    assert "Compliance context" not in brief
    assert "[buyer:" not in brief
    assert "mailto:" not in brief
