from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_site_modes_are_lazy_and_do_not_refetch_everything_on_focus():
    source = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert 'lazy(() => import("./pages/MarketingHome")' in source
    assert 'lazy(() => import("./pages/StorefrontPage")' in source
    assert 'lazy(() => import("./pages/CommercePortalPage")' in source
    assert 'lazy(() => import("./App"))' in source
    assert "refetchOnWindowFocus: false" in source


def test_wholesale_queries_and_heavy_tabs_are_loaded_only_when_needed():
    source = (ROOT / "frontend" / "src" / "pages" / "WholesaleOpsPage.tsx").read_text(encoding="utf-8")
    assert 'const inventoryNeeded=tab==="overview"||tab==="inventory"' in source
    assert 'const commercialNeeded=tab==="overview"||tab==="customers"' in source
    assert 'const storefrontNeeded=tab==="overview"||tab==="storefront"' in source
    assert "enabled:inventoryNeeded" in source
    assert "enabled:commercialNeeded" in source
    assert "enabled:storefrontNeeded" in source
    assert 'lazy(() => import("./OrdersPage")' in source
    assert 'lazy(() => import("./WarehousePickPackPage")' in source
    assert 'lazy(() => import("../components/CommerceStorefrontManager")' in source
