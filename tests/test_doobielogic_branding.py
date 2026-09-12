from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_shell_uses_doobielogic_brand_without_renaming_storage_keys():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    auth = (ROOT / "frontend" / "src" / "components" / "AuthGate.tsx").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    brand_css = (ROOT / "frontend" / "src" / "brand-image.css").read_text(encoding="utf-8")

    # Existing DOM structure remains compatible while the DL tile is visually
    # backed by the same canonical image used throughout DoobieLogic.
    assert '<span>DL</span><strong>DoobieLogic</strong>' in shell
    assert '<div className="eyebrow">DoobieLogic</div>' in shell
    assert '<span>DL</span><strong>DoobieLogic</strong>' in auth
    assert '/doobielogic-logo.webp' in brand_css
    assert 'IMG_7158.PNG' not in brand_css
    assert '<title>DoobieLogic | Cannabis ERP &amp; Operations Software</title>' in index

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
    marketing_nav = (ROOT / "frontend" / "src" / "components" / "marketing" / "MarketingNav.tsx").read_text(encoding="utf-8")
    seo = (ROOT / "frontend" / "src" / "lib" / "seo.ts").read_text(encoding="utf-8")
    brand = (ROOT / "frontend" / "src" / "lib" / "brand.ts").read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    site_mode = (ROOT / "frontend" / "src" / "lib" / "siteMode.ts").read_text(encoding="utf-8")

    assert 'rel="icon"' in index
    assert 'property="og:image"' in index
    assert 'name="twitter:image"' in index
    # The favicon retains the canonical app mark; social cards and the modular
    # marketing navigation use optimized local derivatives of the same brand.
    assert 'rel="icon" type="image/webp" href="/doobielogic-logo.webp"' in index
    assert 'rel="apple-touch-icon" href="/doobielogic-logo.webp"' in index
    assert 'property="og:image" content="https://doobielogic.io/marketing/doobielogic-brand.png"' in index
    assert 'name="twitter:image" content="https://doobielogic.io/marketing/doobielogic-brand.png"' in index
    assert '/marketing/doobielogic-brand.png' in seo
    assert (ROOT / "frontend" / "public" / "marketing" / "doobielogic-brand.png").is_file()
    assert (ROOT / "frontend" / "public" / "marketing" / "brand.webp").is_file()
    assert 'IMG_7158.PNG' not in index
    assert '<MarketingNav />' in marketing
    assert '<MarketingBrand />' in marketing
    assert 'src="/marketing/brand.webp"' in marketing_nav
    assert 'aria-label="DoobieLogic home"' in marketing_nav
    assert 'raw.githubusercontent.com' not in marketing_nav
    assert 'BRAND_IMAGE_URL = "/doobielogic-logo.webp"' in brand
    assert 'https://ops.doobielogic.io/' in brand
    assert 'isMarketingHost(window.location.hostname)' in main
    assert '"doobielogic.io"' in site_mode
    assert '"www.doobielogic.io"' in site_mode
