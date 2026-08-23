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
