import pandas as pd

from modules.buyer_assortment import build_assortment_priorities, coalesce_duplicate_columns


def test_duplicate_export_columns_are_coalesced_without_ambiguous_series():
    frame = pd.DataFrame(
        [
            ["Blue Dream", "", "Flower", "", 12],
            ["GMO", "GMO", "", "Flower", 8],
        ],
        columns=["Product", " product ", "Category", "category", "Quantity"],
    )

    result = coalesce_duplicate_columns(frame)

    assert result.columns.tolist() == ["product", "category", "quantity"]
    assert result["product"].tolist() == ["Blue Dream", "GMO"]
    assert result["category"].tolist() == ["Flower", "Flower"]


def test_priorities_name_size_strain_and_product_format_at_a_glance():
    products = pd.DataFrame(
        [
            {
                "product_name": "House Hybrid 14g",
                "category": "flower",
                "strain_type": "hybrid",
                "package_size": "14g",
                "avg_daily_units": 2.0,
                "on_hand_units": 6,
                "units_sold": 60,
            },
            {
                "product_name": "Sativa Disposable 2g",
                "category": "vapes",
                "strain_type": "sativa disposable",
                "package_size": "2g",
                "avg_daily_units": 1.0,
                "on_hand_units": 2,
                "units_sold": 30,
            },
        ]
    )

    result = build_assortment_priorities(products, target_cover_days=28)

    assert "14g Hybrid Flower" in result["Need"].tolist()
    assert "2g Sativa Disposable Vape" in result["Need"].tolist()
    flower = result[result["Need"] == "14g Hybrid Flower"].iloc[0]
    assert flower["Recommended units"] == 50
    assert flower["Days of cover"] == 3.0


def test_priorities_roll_multiple_skus_into_one_assortment_need():
    products = pd.DataFrame(
        [
            {
                "product_name": "Hybrid A 3.5g",
                "category": "flower",
                "strain_type": "hybrid",
                "package_size": "3.5g",
                "avg_daily_units": 1.0,
                "on_hand_units": 3,
                "units_sold": 30,
            },
            {
                "product_name": "Hybrid B 3.5g",
                "category": "flower",
                "strain_type": "hybrid",
                "package_size": "3.5g",
                "avg_daily_units": 2.0,
                "on_hand_units": 6,
                "units_sold": 60,
            },
        ]
    )

    result = build_assortment_priorities(products, target_cover_days=14)

    assert len(result) == 1
    assert result.iloc[0]["Need"] == "3.5g Hybrid Flower"
    assert result.iloc[0]["SKUs"] == 2
    assert result.iloc[0]["Recommended units"] == 33


def test_priorities_are_empty_when_demand_does_not_require_a_purchase():
    products = pd.DataFrame(
        [
            {
                "product_name": "Covered",
                "category": "edibles",
                "strain_type": "hybrid gummy",
                "package_size": "100mg",
                "avg_daily_units": 1.0,
                "on_hand_units": 40,
                "units_sold": 30,
            }
        ]
    )
    assert build_assortment_priorities(products, target_cover_days=28).empty


def test_priorities_do_not_treat_unknown_inventory_as_zero_stock():
    products = pd.DataFrame(
        [
            {
                "product_name": "Sales-only Product",
                "category": "flower",
                "strain_type": "sativa",
                "package_size": "14g",
                "avg_daily_units": 3.0,
                "on_hand_units": None,
                "units_sold": 90,
            }
        ]
    )
    assert build_assortment_priorities(products).empty
