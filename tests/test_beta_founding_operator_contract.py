from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_beta_page_is_a_measured_founding_operator_program():
    page = (ROOT / "frontend/src/pages/BetaPartnerPage.tsx").read_text(encoding="utf-8")

    for token in (
        "DoobieLogic Founding Operator Beta",
        "guided implementation",
        "no subscription fee during the approved beta period",
        "No positive testimonial required",
        "The trade is real usage, not praise.",
        "establish a baseline",
        "30 / 60 / 90 days",
        "Primary pilot workflow",
        'name="primary_workflow"',
        "Desired start",
        'name="timeline"',
        "Any testimonial or case study requires separate approval",
        "workflow-baseline and implementation-fit call",
    ):
        assert token in page


def test_homepage_funnel_uses_founding_operator_language():
    nav = (ROOT / "frontend/src/components/marketing/MarketingNav.tsx").read_text(encoding="utf-8")
    content = (ROOT / "frontend/src/components/marketing/content.ts").read_text(encoding="utf-8")

    assert 'href="/beta#apply"' in nav
    assert "Founding beta" in nav
    assert "Apply through the Founding Operator Beta." in content
    assert "first workflow to prove" in content
    assert "30 / 60 / 90 days" in content


def test_beta_application_captures_workflow_and_start_window():
    router = (ROOT / "backend/app/routers/beta.py").read_text(encoding="utf-8")

    assert "primary_workflow: str" in router
    assert "timeline: str" in router
    assert "Primary pilot workflow:" in router
    assert "Desired beta start:" in router
