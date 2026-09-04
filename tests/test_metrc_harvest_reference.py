from __future__ import annotations

from pathlib import Path

import pytest

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

    assert transport.calls == [("harvests/v2/waste/types", {"pageSize": 100, "pageNumber": 1})]
    assert result["items"] == ["Plant Material", "Trim"]
    assert result["bounded_page_size"] == 100
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


def test_harvest_ui_requires_provider_waste_type_selector():
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend" / "src" / "components" / "MetrcHarvestControls.tsx").read_text(encoding="utf-8")

    assert "/api/v1/metrc-harvest/waste-types" in source
    assert "Choose exact waste type" in source
    assert "providerTypes.includes(form.waste_type)" in source
    assert "<label>Metrc waste type<select" in source
