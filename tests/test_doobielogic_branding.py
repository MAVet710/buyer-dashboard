from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_shell_uses_doobielogic_brand_without_renaming_storage_keys():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    auth = (ROOT / "frontend" / "src" / "components" / "AuthGate.tsx").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    brand_css = (ROOT / "frontend" / "src" / "brand-image.css").read_text(encoding="utf-8")

    # Existing DOM structure remains compatible while the old DL tile is visually
    # replaced by the same image used by the legacy Streamlit brand.
    assert '<span>DL</span><strong>DoobieLogic</strong>' in shell
    assert '<div className="eyebrow">DoobieLogic</div>' in shell
    assert '<span>DL</span><strong>DoobieLogic</strong>' in auth
    assert 'IMG_7158.PNG' in brand_css
    assert '<title>DoobieLogic | Cannabis Operations Intelligence</title>' in index

    assert '<span>BD</span><strong>Buyer Dash</strong>' not in shell
    assert '<span>BD</span><strong>Buyer Dash</strong>' not in auth
    assert '<title>Buyer Dash</title>' not in index

    # Compatibility storage keys are intentionally retained so the brand rename
    # cannot sign users out or discard their current organization/facility context.
    assert 'buyer-dash-organization' in shell
    assert 'buyer-dash-facility' in shell
    assert 'buyer-dash-trial-token' in auth


def test_public_site_uses_brand_image_for_favicon_and_share_preview():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    marketing = (ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx").read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    site_mode = (ROOT / "frontend" / "src" / "lib" / "siteMode.ts").read_text(encoding="utf-8")

    assert 'rel="icon"' in index
    assert 'property="og:image"' in index
    assert 'name="twitter:image"' in index
    assert index.count('IMG_7158.PNG') >= 3
    assert 'BRAND_IMAGE_URL' in marketing
    assert 'https://ops.doobielogic.io/' in (ROOT / "frontend" / "src" / "lib" / "brand.ts").read_text(encoding="utf-8")
    assert 'isMarketingHost(window.location.hostname)' in main
    assert '"doobielogic.io"' in site_mode
    assert '"www.doobielogic.io"' in site_mode
