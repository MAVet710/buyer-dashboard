from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MarketDataset:
    name: str
    source_url: str
    rows: list[dict[str, Any]]
    fetched_at: str


class MassachusettsCCCProvider:
    """Public Massachusetts Cannabis Control Commission market-data provider.

    The provider is deliberately isolated from Buyer Intelligence so public-source
    failures can never take down store-level recommendations.
    """

    state = "MA"
    source_name = "Massachusetts Cannabis Control Commission"
    sales_url = "https://masscannabiscontrol.com/resource/a_sales_au_gross.json"
    price_url = "https://masscannabiscontrol.com/resource/a_sales_au_price_per_gram.json"

    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    def _fetch_json(self, url: str) -> list[dict[str, Any]]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "DoobieLogic-Market-Intelligence/1.0",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - fixed trusted government source
            payload = response.read()
        decoded = json.loads(payload.decode("utf-8-sig"))
        if not isinstance(decoded, list):
            raise ValueError("CCC market endpoint returned an unexpected payload shape")
        return [row for row in decoded if isinstance(row, dict)]

    def fetch_sales(self) -> MarketDataset:
        return MarketDataset(
            name="adult_use_sales_by_day_and_product_type",
            source_url=self.sales_url,
            rows=self._fetch_json(self.sales_url),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    def fetch_prices(self) -> MarketDataset:
        return MarketDataset(
            name="average_retail_price_per_gram",
            source_url=self.price_url,
            rows=self._fetch_json(self.price_url),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
