from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_api_propagates_active_buyer_data_mode():
    api = (ROOT / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    shell = (ROOT / "frontend" / "src" / "components" / "AppShell.tsx").read_text(encoding="utf-8")

    assert '"X-DoobieLogic-Data-Mode": buyerDataMode()' in api
    assert 'localStorage.getItem("buyer-dash-data-mode") === "Dutchie Live"' in api
    assert 'localStorage.setItem("buyer-dash-data-mode", dataMode)' in shell
    assert 'window.dispatchEvent(new CustomEvent("buyer-dash-data-mode"' in shell


def test_dutchie_live_never_silently_falls_back_to_upload_backed_buyer_routes():
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")

    for route in (
        "/buyer-parity",
        "/buyer-legacy-overview",
        "/slow-movers-parity",
        "/buying-budget-parity",
        "/po-parity",
        "/executive-reports",
    ):
        assert route in main
    assert 'request.headers.get("X-DoobieLogic-Data-Mode")' in main
    assert "Live Dutchie API fetching is not yet implemented in the web runtime" in main
    assert "status_code=409" in main
