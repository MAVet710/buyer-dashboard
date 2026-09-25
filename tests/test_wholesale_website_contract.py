from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_wholesale_site_has_brand_partnership_and_order_journey():
    page = (ROOT / "frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    sections = (ROOT / "frontend/src/components/WholesaleWebsiteSections.tsx").read_text(encoding="utf-8")

    for token in (
        "WholesalePartnerSection",
        "WholesaleProcessSection",
        "#wholesale-partners",
        "#wholesale-process",
        "#catalog",
        "#order-request",
    ):
        assert token in page

    for token in (
        "WHOLESALE PARTNERSHIP",
        "orderable now",
        "COA-backed listings",
        "volume-priced products",
        "HOW WHOLESALE WORKS",
        "Browse live inventory",
        "Sales review",
        "Fulfillment & status",
        "Approval-gated by design.",
    ):
        assert token in sections


def test_storefront_studio_preview_matches_public_partnership_and_process_layers():
    manager = (ROOT / "frontend/src/components/CommerceStorefrontManager.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/storefront-studio-v2.css").read_text(encoding="utf-8")

    for token in (
        "studio-preview-partnership",
        "WHOLESALE PARTNERSHIP",
        "studio.partnership_heading",
        "studio.partnership_body",
        "studio-preview-process",
        "Catalog → request → approval → fulfillment",
    ):
        assert token in manager

    assert ".studio-preview-partnership" in css
    assert ".studio-preview-process" in css


def test_public_storefront_gets_brand_seo_instead_of_private_ops_noindex():
    page = (ROOT / "frontend/src/pages/StorefrontPage.tsx").read_text(encoding="utf-8")
    seo = (ROOT / "frontend/src/lib/seo.ts").read_text(encoding="utf-8")

    assert "configurePublicStorefrontSeo" in page
    assert "canonical:storefront.url" in page.replace(" ", "")
    assert "Wholesale Cannabis Catalog" in seo
    assert 'upsertMeta("robots", PUBLIC_ROBOTS)' in seo
    assert '"twitter:card": "summary_large_image"' in seo
