from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_buyer_legacy_filter_surface_matches_operator_recording_contract():
    source = (ROOT / "frontend" / "src" / "pages" / "BuyerOperationsPage.tsx").read_text(encoding="utf-8")
    source = source.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    for label in [
        "Buyer Filters & Settings",
        "Search (SKU / Product / Brand)",
        "Velocity window",
        "Last 56 days",
        "Show top N",
        "$ on hand ↓",
        "Category / Subcategory",
        "Vendor / Brand",
        "Expiration window",
        "On-hand > 0",
        "DOH min (days)",
        "DOH max (days)",
        "Overstock SKUs",
        "Expiring <60d",
        "SKU(s) (velocity window:",
        "Show all columns",
        "Run Doobie Inventory Check",
    ]:
        assert label in source
    assert "filteredSkuRows" in source
    assert "filteredInventoryBase" in source
    assert "doobiePayload" in source


def test_doobie_inventory_check_uses_same_deterministic_buyer_filters():
    source = (ROOT / "backend" / "app" / "routers" / "buyer_parity_actions.py").read_text(encoding="utf-8")
    for contract in [
        "brands: list[str]",
        "search: str",
        "expiration_window: str",
        "on_hand_only: bool",
        "min_doh: float",
        "max_doh: float",
        "velocity_window: int",
        "top_n: int",
        "sort_by: str",
        "sku_inventory_view",
        "recommended_reorder_qty",
        '"filtered_rows"',
    ]:
        assert contract in source
