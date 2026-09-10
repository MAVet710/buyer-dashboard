from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_control_tower_exceptions_open_the_resolution_surface():
    page = (ROOT / "frontend/src/pages/OperationsControlTowerPage.tsx").read_text(encoding="utf-8")
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

    assert '<OperationsControlTowerPage onNavigate={navigate} />' in app
    for marker in (
        'action="Reconcile now"',
        'onOpen={()=>onNavigate("Compliance")}',
        'action="Review action"',
        'onOpen={()=>onOpenTab("Action Center")}',
        'action="Review deviation"',
        'onOpen={()=>onOpenTab("SOP Control")}',
        'action="Review labels"',
        'action="Inspect machines"',
        "Ranked work with a direct path to the exact resolution surface.",
    ):
        assert marker in page


def test_control_tower_counts_cross_domain_exceptions():
    page = (ROOT / "frontend/src/pages/OperationsControlTowerPage.tsx").read_text(encoding="utf-8")

    assert "summary?.traceability.needs_reconciliation" in page
    assert "summary?.labels.failures" in page
    assert "machines.reduce" in page
    assert "exceptionCount===0" in page
