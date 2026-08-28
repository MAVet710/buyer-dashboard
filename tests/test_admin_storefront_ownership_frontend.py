from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "AdminToolsPage.tsx").read_text(encoding="utf-8")


def test_admin_tools_exposes_storefront_tenant_ownership_controls():
    assert "Storefront ownership &amp; hostname routing" in SOURCE
    assert '"/api/v1/admin/storefronts"' in SOURCE
    assert "/ownership`" in SOURCE
    assert "Organization<select" in SOURCE
    assert "Commercial facility<select" in SOURCE
    assert "Save storefront ownership" in SOURCE


def test_admin_tools_warns_before_cross_tenant_catalog_or_history_damage():
    assert "order-request history" in SOURCE
    assert "Clear the existing catalog before moving organizations" in SOURCE
    assert "Product IDs from the old organization will not be carried into the new tenant" in SOURCE
