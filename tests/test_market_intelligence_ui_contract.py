from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_buyer_intelligence_uses_native_market_pulse_not_headset_link():
    page = (ROOT / "frontend/src/pages/BuyingRecommendationsPage.tsx").read_text(encoding="utf-8")
    assert "MarketPulse" in page
    assert "/api/v1/buyer-parity/market-intelligence" in page
    assert "headset.io" not in page
    assert "Optional live market references" not in page


def test_buyer_intelligence_api_exposes_fail_soft_market_endpoint():
    router = (ROOT / "backend/app/routers/buyer_parity.py").read_text(encoding="utf-8")
    assert "build_market_intelligence" in router
    assert '@router.get("/market-intelligence")' in router


def test_buyer_brief_receives_secondary_native_market_evidence():
    actions = (ROOT / "backend/app/routers/buyer_parity_actions.py").read_text(encoding="utf-8")
    assert "_buyer_market_context" in actions
    assert 'bounded_context["market_intelligence"] = market_context' in actions
    assert '"priority": "secondary_to_store_sales_and_inventory"' in actions
