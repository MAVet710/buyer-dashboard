from __future__ import annotations

from services.market_data.ma_ccc import MarketDataset
from services.market_data.market_intelligence import build_market_intelligence, normalize_category


class FakeProvider:
    state = "MA"
    source_name = "Massachusetts Cannabis Control Commission"

    def fetch_sales(self):
        return MarketDataset(
            name="sales",
            source_url="https://example.test/sales.json",
            fetched_at="2026-09-01T00:00:00+00:00",
            rows=[
                {"SaleDate": "2026-07-01", "ProductCategory": "Buds", "GrossSales": "100", "CCCLastUpdated": "2026-08-26"},
                {"SaleDate": "2026-07-20", "ProductCategory": "Buds", "GrossSales": "100", "CCCLastUpdated": "2026-08-26"},
                {"SaleDate": "2026-08-10", "ProductCategory": "Buds", "GrossSales": "150", "CCCLastUpdated": "2026-08-26"},
                {"SaleDate": "2026-08-25", "ProductCategory": "Buds", "GrossSales": "150", "CCCLastUpdated": "2026-08-26"},
            ],
        )

    def fetch_prices(self):
        return MarketDataset(
            name="prices",
            source_url="https://example.test/prices.json",
            fetched_at="2026-09-01T00:00:00+00:00",
            rows=[
                {"YearMonth": "2026-06", "AverageRetailPriceperGm": "3.87", "CCCLastUpdated": "2026-08-26"},
                {"YearMonth": "2026-07", "AverageRetailPriceperGm": "3.83", "CCCLastUpdated": "2026-08-26"},
            ],
        )


def test_normalize_category_maps_ccc_terms_to_doobielogic_categories():
    assert normalize_category("Buds") == "Flower"
    assert normalize_category("Raw Pre-Rolls") == "Pre-Rolls"
    assert normalize_category("Vape Product") == "Vapes"


def test_market_intelligence_compares_public_market_with_store_evidence():
    result = build_market_intelligence(
        store_category_rows=[{"category": "Flower", "units_sold": 70, "revenue": 1400}],
        store_product_rows=[{"category": "Flower", "days_of_cover": 14}],
        lookback_days=30,
        provider=FakeProvider(),
    )
    assert result["status"] == "available"
    assert result["state"] == "MA"
    assert result["average_retail_price_per_gram"] == 3.83
    assert result["average_retail_price_change"] < 0
    flower = next(row for row in result["categories"] if row["category"] == "Flower")
    assert flower["market_growth"] > 0
    assert flower["signal"] == "BUY"


def test_market_intelligence_fails_soft_when_provider_is_down():
    class DownProvider(FakeProvider):
        def fetch_sales(self):
            raise TimeoutError("public source unavailable")

    result = build_market_intelligence(
        store_category_rows=[],
        store_product_rows=[],
        lookback_days=30,
        provider=DownProvider(),
    )
    assert result["status"] == "unavailable"
    assert result["categories"] == []
    assert "unaffected" in result["message"]
