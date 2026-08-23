from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_shell_uses_doobielogic_brand_without_renaming_storage_keys():
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    auth = (ROOT / "frontend" / "src" / "components" / "AuthGate.tsx").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert '<span>DL</span><strong>DoobieLogic</strong>' in shell
    assert '<div className="eyebrow">DoobieLogic</div>' in shell
    assert '<span>DL</span><strong>DoobieLogic</strong>' in auth
    assert '<title>DoobieLogic</title>' in index

    assert '<span>BD</span><strong>Buyer Dash</strong>' not in shell
    assert '<span>BD</span><strong>Buyer Dash</strong>' not in auth
    assert '<title>Buyer Dash</title>' not in index

    # Compatibility storage keys are intentionally retained so the brand rename
    # cannot sign users out or discard their current organization/facility context.
    assert 'buyer-dash-organization' in shell
    assert 'buyer-dash-facility' in shell
    assert 'buyer-dash-trial-token' in auth
