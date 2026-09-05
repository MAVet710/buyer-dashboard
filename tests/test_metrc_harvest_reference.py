from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routers import metrc_harvest_actions as harvest_router
from backend.app.services.metrc_harvest_reference import (
    MetrcHarvestReferenceError,
    fetch_harvest_waste_types,
)


class FakeTransport:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict):
        self.calls.append((path, params))
        return self.result


def test_harvest_waste_types_use_exact_fixed_path_and_unique_provider_names():
    transport = FakeTransport({
        "ok": True,
        "http_status": 200,
        "correlation_id": "corr-1",
        "payload": {
            "Data": [
                {"Name": "Plant Material"},
                {"Name": "Trim"},
                {"Name": "trim"},
                {"Name": ""},
                {"Other": "ignored"},
            ]
        },
    })

    result = fetch_harvest_waste_types(
        state="MA",
        environment="sandbox",
        integrator_api_key="integrator",
        user_api_key="user",
        transport=transport,
    )

    assert transport.calls == [("harvests/v2/waste/types", {"pageSize": 20, "pageNumber": 1})]
    assert result["items"] == ["Plant Material", "Trim"]
    assert result["bounded_page_size"] == 20
    assert result["correlation_id"] == "corr-1"


def test_harvest_waste_types_fail_closed_on_provider_read_error():
    transport = FakeTransport({"ok": False, "message": "Metrc unavailable"})

    with pytest.raises(MetrcHarvestReferenceError, match="Metrc unavailable"):
        fetch_harvest_waste_types(
            state="MA",
            environment="sandbox",
            integrator_api_key="integrator",
            user_api_key="user",
            transport=transport,
        )


def test_harvest_waste_types_fail_closed_when_provider_returns_no_usable_names():
    transport = FakeTransport({"ok": True, "http_status": 200, "payload": {"Data": [{"Id": 1}]}})

    with pytest.raises(MetrcHarvestReferenceError, match="no usable harvest waste types"):
        fetch_harvest_waste_types(
            state="MA",
            environment="sandbox",
            integrator_api_key="integrator",
            user_api_key="user",
            transport=transport,
        )


def test_server_requires_exact_current_provider_waste_type(monkeypatch):
    metrc = SimpleNamespace(state="MA", environment="sandbox", integrator_api_key="integrator", user_api_key="user")
    monkeypatch.setattr(harvest_router, "_waste_types", lambda _metrc: {"items": ["Plant Material", "Trim"]})
    valid = harvest_router.HarvestActionRequest(
        operation_type="harvest_waste",
        harvest_id="harvest-1",
        waste_type="Trim",
        waste_weight_g=1,
        reason="Waste",
    )
    harvest_router._validate_waste_type(valid, metrc)

    invalid = valid.model_copy(update={"waste_type": "trim"})
    with pytest.raises(HTTPException) as exc_info:
        harvest_router._validate_waste_type(invalid, metrc)
    assert exc_info.value.status_code == 422
    assert "exact current Metrc harvest waste type" in str(exc_info.value.detail)


def test_non_waste_actions_do_not_load_waste_reference_data(monkeypatch):
    called = False

    def fail_if_called(_metrc):
        nonlocal called
        called = True
        raise AssertionError("non-waste actions must not load waste types")

    monkeypatch.setattr(harvest_router, "_waste_types", fail_if_called)
    payload = harvest_router.HarvestActionRequest(
        operation_type="harvest_finish",
        harvest_id="harvest-1",
        all_waste_reported=True,
        reason="Finish harvest",
    )
    harvest_router._validate_waste_type(payload, object())
    assert called is False


def test_harvest_ui_requires_provider_waste_type_selector():
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend" / "src" / "components" / "MetrcHarvestControls.tsx").read_text(encoding="utf-8")

    assert "/api/v1/metrc-harvest/waste-types" in source
    assert "Choose exact waste type" in source
    assert "providerTypes.includes(form.waste_type)" in source
    assert "<label>Metrc waste type<select" in source
