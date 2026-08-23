from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.auth import RequestContext
from backend.app.routers.buyer_parity import _require_available_data_mode


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_buyer_data_mode_is_carried_from_web_header_into_request_context():
    api = read("frontend/src/lib/api.ts")
    auth = read("backend/app/auth.py")

    assert '"X-DoobieLogic-Data-Mode": buyerDataMode()' in api
    assert 'alias="X-DoobieLogic-Data-Mode"' in auth
    assert 'data_mode: str = "Uploads"' in auth


def test_dutchie_stub_mode_never_silently_falls_back_to_uploaded_sources():
    context = RequestContext("user", "org", "facility", "buyer", "Dutchie Live")
    with pytest.raises(HTTPException) as exc:
        _require_available_data_mode(context)
    assert exc.value.status_code == 503
    assert "live data fetch is not yet implemented" in str(exc.value.detail)

    _require_available_data_mode(RequestContext("user", "org", "facility", "buyer", "Uploads"))


def test_data_mode_switch_refetches_active_web_queries():
    app = read("frontend/src/App.tsx")
    shell = read("frontend/src/components/AppShell.tsx")
    streamlit = read("modules/navigation/workspace_shell.py")

    assert 'window.dispatchEvent(new CustomEvent("buyer-dash-data-mode"' in shell
    assert 'window.addEventListener("buyer-dash-data-mode", refreshForDataMode)' in app
    assert "client.invalidateQueries()" in app
    assert 'modes = ["📁 Uploads", "🔴 Dutchie Live"]' in streamlit


def test_every_upload_backed_buyer_surface_uses_the_same_data_mode_guard():
    buyer = read("backend/app/routers/buyer_parity.py")
    slow = read("backend/app/routers/slow_movers_parity.py")
    budget = read("backend/app/routers/buying_budget_parity.py")
    po = read("backend/app/routers/po_parity.py")
    reports = read("backend/app/routers/executive_reports.py")

    assert "_require_available_data_mode(context)" in buyer
    assert "from .buyer_parity import _require_available_data_mode" in slow
    assert "_require_available_data_mode(context)" in slow
    assert "from .buyer_parity import _require_available_data_mode" in budget
    assert "_require_available_data_mode(context)" in budget
    assert "from .buyer_parity import _model" in po
    assert "from .buyer_parity import _model as buyer_model" in reports
    assert "buyer_model(" in reports
    assert "context," in reports
    assert "engine," in reports
