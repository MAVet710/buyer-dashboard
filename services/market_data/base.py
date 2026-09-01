from __future__ import annotations

from typing import Protocol

from .ma_ccc import MarketDataset


class MarketProvider(Protocol):
    state: str
    source_name: str

    def fetch_sales(self) -> MarketDataset: ...

    def fetch_prices(self) -> MarketDataset: ...
