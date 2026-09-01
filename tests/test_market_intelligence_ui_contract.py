from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_buyer_intelligence_uses_native_market_pulse_not_headset_link():
    page = (ROOT / "frontend/src/pages/BuyingRecommendationsPage.tsx").read_text(encoding="utf-8")
    assert "MarketPulse" in page
    assert "headset.io" not in page
    assert "Optional live market references" not in page


def test_buyer_intelligence_api_returns_market_payload():
    router = (ROOT / "backend/app/routers/buyer_parity.py").read_text(encoding="utf-8")
    assert "build_market_intelligence" in router
    assert '"market"' in router
