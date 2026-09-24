from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_product_proof_includes_real_extraction_video():
    marketing = (ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx").read_text(encoding="utf-8")
    showcase = (ROOT / "frontend" / "src" / "components" / "marketing" / "ProductShowcase.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "src" / "marketing-home.css").read_text(encoding="utf-8")
    media = ROOT / "frontend" / "public" / "marketing"

    assert '"extraction"' in showcase
    assert '"Extraction workspace"' in showcase
    assert 'video: "extraction-workspace.webm"' in showcase
    assert 'fallbackVideo: "extraction-workspace.mp4"' in showcase
    assert 'poster: "extraction-workspace-poster.png"' in showcase
    for attribute in ("autoPlay", "muted", "loop", "playsInline"):
        assert attribute in showcase
    assert 'type="video/webm"' in showcase
    assert 'type="video/mp4"' in showcase
    assert "See the run before" in marketing
    assert "you read the report." in marketing
    assert "Real extraction workflow" in marketing
    assert "Input-to-output traceability" in marketing
    assert '<ProductShowcase' in marketing
    assert "activeView={productWorkspace}" in marketing
    assert "onViewChange={setProductWorkspace}" in marketing
    assert '.mh-product-video' in css
    assert 'aria-selected="true"' in css
    assert (media / "extraction-workspace.webm").stat().st_size > 100_000
    assert (media / "extraction-workspace.mp4").stat().st_size > 100_000
    assert (media / "extraction-workspace-poster.png").stat().st_size > 50_000
